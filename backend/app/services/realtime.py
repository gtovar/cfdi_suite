import os
import time

from pusher import Pusher

# Cliente Pusher perezoso y tolerante a credenciales ausentes (mismo criterio
# que routers/batch.py): sin credenciales, el push en tiempo real se apaga
# pero el resto del flujo sigue funcionando.
_pusher = None
_init_done = False


def get_pusher():
    global _pusher, _init_done
    if not _init_done:
        _init_done = True
        app_id = os.getenv("PUSHER_APP_ID")
        key = os.getenv("PUSHER_KEY")
        secret = os.getenv("PUSHER_SECRET")
        if app_id and key and secret:
            _pusher = Pusher(
                app_id=app_id,
                key=key,
                secret=secret,
                cluster=os.getenv("PUSHER_CLUSTER", "us2"),
                ssl=True,
            )
        else:
            print("[Pusher Warning] Faltan variables de entorno; progreso en tiempo real desactivado.")
    return _pusher


def publish_batch_progress(batch_id: str, payload: dict) -> None:
    """Publica el avance de un lote ZIP→PDF al canal `pdf-batch-{batch_id}`.

    Es una llamada síncrona (la librería pusher es síncrona) — invocar vía
    asyncio.to_thread desde código async. Los errores se tragan a propósito:
    perder un tick de progreso nunca debe tumbar la generación del PDF.
    """
    client = get_pusher()
    if not client:
        return
    try:
        client.trigger(f"pdf-batch-{batch_id}", "progress", payload)
    except Exception as e:
        print(f"[Pusher Error] progreso del batch {batch_id} no publicado: {e}")


# Throttle en memoria del proceso, sin Redis -- ver publish_batch_signal.
# Por batch_id, nunca limpiado explícitamente (los batch_id son UUIDs
# efímeros; el diccionario se descarta solo cuando la instancia de Cloud Run
# recicla). Aceptado a propósito: agregar limpieza activa sería más código
# para un crecimiento acotado y de vida corta, no hay evidencia de que
# importe.
_last_signal_at: dict[str, float] = {}
_SIGNAL_MIN_INTERVAL_SECONDS = 3.0


def publish_batch_signal(batch_id: str, kind: str) -> None:
    """Aviso MÍNIMO de que algo cambió en el batch -- 'job_done' o
    'job_error' -- SIN NINGUNA dependencia de Redis (a diferencia de
    publish_batch_progress, cuyo payload rico sí depende de contadores de
    Redis). Encontrado 2026-07-25: `_publish_batch_tick`/`publish_batch_tick`
    (que sí llaman a publish_batch_progress al final) viven completos dentro
    de `safe_redis_call` en los call sites de pdf.py/batch_shard_worker.py --
    si Redis está degradado, esa llamada se corta ANTES de llegar a Pusher,
    y el usuario se queda sin ningún aviso en vivo hasta el respaldo
    periódico de 75s del frontend (`fetchSnapshot`, ver pdf-download.ts).

    Este aviso se llama SIEMPRE, nunca envuelto en safe_redis_call/is_degraded()
    -- Pusher es un servicio externo sin relación con Redis, no hay razón
    para que comparta su destino. El payload es deliberadamente pobre (sin
    contador, sin lista de IDs) porque esos datos SÍ requieren Redis para
    calcularse correctamente (contador atómico compartido entre instancias)
    -- eso sigue siendo un límite real, no se resuelve aquí. El frontend, al
    recibir esta señal, solo sabe "algo cambió" y reconcilia contra /status
    (que ya cae a GCS si Redis no responde, ver batch_state_store.py) --
    mismo patrón que ya usa en reconexiones de Pusher (state_change).

    Mismo patrón que ya usaba correctamente app.routers.batch (análisis de
    CFDI): su pusher_client.trigger() vive fuera de safe_redis_call_sync,
    con su propio try/except -- esto lleva pdf.py/batch_shard_worker.py a
    ese mismo criterio, que nunca se les había aplicado.

    Throttle LOCAL (time.monotonic, sin Redis) para no arriesgar el límite
    del plan de Pusher en batches grandes -- solo aplica a 'job_done'; los
    errores (kind='job_error') siempre se publican, igual que
    definitive_error ya salta el throttle del payload rico.
    """
    if kind == "job_done":
        now = time.monotonic()
        last = _last_signal_at.get(batch_id, 0.0)
        if now - last < _SIGNAL_MIN_INTERVAL_SECONDS:
            return
        _last_signal_at[batch_id] = now

    client = get_pusher()
    if not client:
        return
    try:
        client.trigger(f"pdf-batch-{batch_id}", "signal", {"kind": kind})
    except Exception as e:
        print(f"[Pusher Error] señal de batch {batch_id} no publicada: {e}")
