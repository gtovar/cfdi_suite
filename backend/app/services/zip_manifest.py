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


def is_valid_xml_entry(file_info: zipfile.ZipInfo) -> bool:
    if "__MACOSX" in file_info.filename or ".DS_Store" in file_info.filename:
        return False
    return file_info.filename.lower().endswith(".xml")


def compute_job_id(batch_id: str, filename: str) -> str:
    """Determinístico (no uuid4): si Cloud Tasks reintenta una extracción
    completa tras un fallo, o si dos rutas distintas (manifiesto y tarea de
    shard) necesitan llegar al mismo id para el mismo archivo, este cálculo
    siempre da el mismo resultado sin necesitar coordinación."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{batch_id}:{filename}"))


def build_manifest(infolist, batch_id: str) -> dict[str, str]:
    """job_id -> filename, a partir de cualquier iterable de objetos con
    atributo .filename (zipfile.ZipInfo local, o los que devuelve
    remotezip.RemoteZip.infolist() para un ZIP remoto -- misma interfaz)."""
    return {
        compute_job_id(batch_id, file_info.filename): file_info.filename
        for file_info in infolist
        if is_valid_xml_entry(file_info)
    }
