"""
error_reporting.py — un solo camino para los errores que ve el usuario.

Hallazgo #4: ~24 sitios devolvían `str(exc)` dentro de la respuesta HTTP. Eso
le entrega al que llama la traza interna del fallo: rutas del filesystem del
contenedor, URLs y hostnames internos, nombres de bucket, detalles de red de
Diverza y del portal del SAT, y mensajes de librerías que delatan versiones. La
API es anónima y pública, así que ese texto lo lee cualquiera.

La regla es una sola, deliberadamente aburrida:

    el detalle completo va a Sentry, al usuario le llega un mensaje genérico
    en español que describe QUÉ falló, nunca POR QUÉ

"Qué falló" (generar el PDF, consultar el SAT, leer el ZIP) es información que
el usuario necesita para saber si reintentar o cambiar de archivo, y no le dice
nada útil a un atacante. "Por qué" es justamente lo que se está cerrando.

Lo que NO pasa por aquí, a propósito: los mensajes de validación que le repiten
al usuario su propio input ("Emisor XAXX010101000 no encontrado", "width
inválido en columna 'total'"). Ésos no filtran estado interno -- son la API
diciéndole al que llama qué mandó mal -- y borrarlos empeoraría el producto sin
mejorar la seguridad.
"""
from __future__ import annotations

import sentry_sdk


def report(exc: BaseException, *, contexto: str | None = None) -> None:
    """Manda el detalle completo a Sentry. Nunca lanza.

    `contexto` es una etiqueta corta para poder agrupar en Sentry (por ejemplo
    "generar_pdf"); no se le muestra al usuario.
    """
    try:
        if contexto:
            sentry_sdk.set_tag("operacion", contexto)
        sentry_sdk.capture_exception(exc)
    except Exception:
        # El reporte de errores no puede ser, él mismo, una fuente de errores.
        pass
