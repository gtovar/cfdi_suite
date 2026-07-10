import os

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
