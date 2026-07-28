"""
zip_manifest.py — lógica compartida para construir el manifiesto de un batch
(job_id -> nombre de archivo) a partir del listado de un ZIP.

Extraído de app/routers/pdf.py para que el constructor del manifiesto (hoy:
process_zip_in_background, que itera un ZIP ya descargado localmente;
próximamente: un camino que lee el directorio central de un ZIP remoto vía
remotezip) y cada tarea del Cloud Run Job de shards
(app/workers/batch_shard_worker.py) usen EXACTAMENTE la misma regla para
decidir qué es un XML válido y cómo se calcula su job_id. Que ambos lados
diverjan aunque sea en un detalle produciría un job_id sin archivo
correspondiente (o viceversa) -- el peor tipo de bug para depurar, porque se
manifiesta como un batch atorado sin error visible, no como una excepción.
"""
from __future__ import annotations

import uuid
import zipfile
from dataclasses import dataclass
from typing import Iterable


MAX_ZIP_ENTRIES = 2_000
MAX_ZIP_COMPRESSED_BYTES = 512 * 1024 * 1024
MAX_XML_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
# El fixture real compatible de 367 MB declara 7.83 GiB descomprimidos
# (2,000 XMLs, XML máximo 7.27 MB y ratio máximo 23.6x). El procesamiento
# consume XMLs por chunks, así que este tope limita trabajo agregado sin
# exigir que el total resida simultáneamente en memoria.
MAX_ZIP_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_024


class ZipBudgetError(ValueError):
    """El directorio central declara un ZIP fuera del presupuesto permitido.

    ``code`` está pensado para logs y pruebas. El texto que llega al usuario se
    decide en el borde HTTP, para no revelar nombres ni metadata del archivo.
    """

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ValidatedZipManifest:
    """Resultado único de validar el directorio central antes de leer datos."""

    entries: tuple[zipfile.ZipInfo, ...]
    xml_entries: tuple[zipfile.ZipInfo, ...]
    manifest: dict[str, str]


def validate_gcs_zip_size(blob) -> int:
    """Carga metadata GCS y aplica el presupuesto antes de transferir el ZIP.

    ``Blob.reload`` es deliberado: ``bucket.blob`` no conoce el tamaño y no
    basta con confiar en metadata de una llamada anterior o del navegador.
    """
    blob.reload()
    size = blob.size
    if size is None:
        raise ZipBudgetError("unknown_gcs_object_size")
    return validate_zip_compressed_size(size)


def validate_zip_compressed_size(size: int) -> int:
    """Presupuesto común para un ZIP local o un objeto GCS."""
    if not isinstance(size, int) or size < 0:
        raise ZipBudgetError("unknown_gcs_object_size")
    if size > MAX_ZIP_COMPRESSED_BYTES:
        raise ZipBudgetError("compressed_zip_too_large")
    return size


def is_valid_xml_entry(file_info: zipfile.ZipInfo) -> bool:
    if file_info.is_dir():
        return False
    if "__MACOSX" in file_info.filename or ".DS_Store" in file_info.filename:
        return False
    return file_info.filename.lower().endswith(".xml")


def compute_job_id(batch_id: str, filename: str) -> str:
    """Determinístico (no uuid4): si Cloud Tasks reintenta una extracción
    completa tras un fallo, o si dos rutas distintas (manifiesto y tarea de
    shard) necesitan llegar al mismo id para el mismo archivo, este cálculo
    siempre da el mismo resultado sin necesitar coordinación."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{batch_id}:{filename}"))


def inspect_zip_manifest(infolist: Iterable[zipfile.ZipInfo], batch_id: str) -> ValidatedZipManifest:
    """Valida el directorio central completo y construye el manifiesto XML.

    Esta es la única puerta para los caminos local, GCS remoto y Cloud Run
    Job. El presupuesto se evalúa sobre todas las entradas no-directorio para
    que una entrada ignorada no pueda evadir el límite antes de un ``read``.
    """
    entries = tuple(infolist)
    if len(entries) > MAX_ZIP_ENTRIES:
        raise ZipBudgetError("too_many_entries")

    total_uncompressed = 0
    for file_info in entries:
        if file_info.is_dir():
            continue

        file_size = file_info.file_size
        compress_size = file_info.compress_size
        if file_size < 0 or compress_size < 0:
            raise ZipBudgetError("invalid_entry_size")

        total_uncompressed += file_size
        if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise ZipBudgetError("total_uncompressed_too_large")

        if file_size and (compress_size == 0 or file_size / compress_size > MAX_COMPRESSION_RATIO):
            raise ZipBudgetError("compression_ratio_too_high")

        if is_valid_xml_entry(file_info) and file_size > MAX_XML_UNCOMPRESSED_BYTES:
            raise ZipBudgetError("xml_too_large")

    xml_entries = tuple(file_info for file_info in entries if is_valid_xml_entry(file_info))
    manifest = {
        compute_job_id(batch_id, file_info.filename): file_info.filename
        for file_info in xml_entries
    }
    return ValidatedZipManifest(entries=entries, xml_entries=xml_entries, manifest=manifest)


def build_manifest(infolist: Iterable[zipfile.ZipInfo], batch_id: str) -> dict[str, str]:
    """Compatibilidad para llamadores que sólo necesitan ``job_id -> nombre``.

    Todos los llamadores reciben los mismos presupuestos aunque no requieran
    acceder a ``xml_entries``.
    """
    return inspect_zip_manifest(infolist, batch_id).manifest
