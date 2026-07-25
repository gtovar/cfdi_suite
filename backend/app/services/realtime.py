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


# Throttle en memoria del proceso, sin Redis -- ver publish_batch_signal.
# Por batch_id, nunca limpiado explícitamente (los batch_id son UUIDs
# efímeros; el diccionario se descarta solo cuando la instancia de Cloud Run
# recicla). Aceptado a propósito: agregar limpieza activa sería más código
# para un crecimiento acotado y de vida corta, no hay evidencia de que
# importe.
_last_signal_at: dict[str, float] = {}
_SIGNAL_MIN_INTERVAL_SECONDS = 3.0


def publish_batch_signal(batch_id: str, kind: str) -> None:
    """Único evento en vivo del progreso de batch -- 'job_done' o 'job_error'
    -- SIN NINGUNA dependencia de Redis. Se llama SIEMPRE, nunca envuelto en
    safe_redis_call/is_degraded() -- Pusher es un servicio externo sin
    relación con Redis, no hay razón para que comparta su destino.

    2026-07-25: hasta entonces existía también `publish_batch_progress`, un
    segundo evento ('progress') que SÍ cargaba el payload completo
    (done/error/percentage/readyIds) calculado con contadores de Redis, y que
    por vivir dentro de safe_redis_call se perdía por completo si Redis
    estaba degradado. 2026-07-25 (rediseño hint-only, ver PROJECT_STATE.md):
    se eliminó -- este aviso es deliberadamente pobre (sin contador, sin
    lista de IDs) a propósito, no como límite pendiente de resolver: el
    frontend, al recibirlo, solo sabe "algo cambió" y relee /status
    (batch_state_store.get_batch_snapshot, que ya cae a GCS si Redis no
    responde) -- una sola fuente de verdad, un solo camino de lectura, en vez
    de dos canales (dato + aviso) que podían desincronizarse entre sí.

    Mismo patrón que ya usaba correctamente app.routers.batch (análisis de
    CFDI): su pusher_client.trigger() vive fuera de safe_redis_call_sync, con
    su propio try/except.

    Throttle LOCAL (time.monotonic, sin Redis) para no arriesgar el límite
    del plan de Pusher en batches grandes -- solo aplica a 'job_done'; los
    errores (kind='job_error') siempre se publican.
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
