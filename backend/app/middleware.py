"""Protecciones ASGI para cuerpos multipart antes de que Starlette los parsee."""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


MIB = 1024 * 1024

# El presupuesto de archivos se valida de nuevo en cada endpoint. Este margen
# sólo cubre boundaries y headers de multipart, sin convertirlos en memoria de
# archivos permitida.
MULTIPART_OVERHEAD_BYTES = MIB
PDF_SINGLE_XML_MAX_BYTES = 50 * MIB
BATCH_FILE_MAX_BYTES = 20 * MIB
BATCH_TOTAL_MAX_BYTES = 100 * MIB
SAT_XLSX_MAX_BYTES = 10 * MIB
FIEL_TOTAL_MAX_BYTES = 5 * MIB

REQUEST_BODY_LIMITS: dict[str, int] = {
    "/api/cfdi/analyze": PDF_SINGLE_XML_MAX_BYTES + MULTIPART_OVERHEAD_BYTES,
    "/api/cfdi/pdf/start": PDF_SINGLE_XML_MAX_BYTES + MULTIPART_OVERHEAD_BYTES,
    "/api/cfdi/batch/analyze": BATCH_TOTAL_MAX_BYTES + MULTIPART_OVERHEAD_BYTES,
    "/api/cfdi/batch/diot": BATCH_TOTAL_MAX_BYTES + MULTIPART_OVERHEAD_BYTES,
    "/api/sat/enquiry/batch": SAT_XLSX_MAX_BYTES + MULTIPART_OVERHEAD_BYTES,
    "/api/fiel/configure": FIEL_TOTAL_MAX_BYTES + MULTIPART_OVERHEAD_BYTES,
}


class RequestBodyTooLarge(Exception):
    pass


class RouteBodySizeLimitMiddleware:
    """Corta el stream antes de que el parser multipart cree temporales.

    ``Content-Length`` permite rechazar inmediatamente. Si no está presente o
    es incorrecto, el wrapper de ``receive`` conserva el mismo límite sobre
    cada chunk que llega desde ASGI.
    """

    def __init__(self, app: ASGIApp, limits: dict[str, int] | None = None) -> None:
        self.app = app
        self.limits = limits or REQUEST_BODY_LIMITS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or (limit := self.limits.get(scope["path"])) is None:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > limit:
                    await self._send_413(send)
                    return
            except ValueError:
                # Un header inválido no es prueba de un tamaño seguro: el
                # contador del stream de abajo sigue siendo autoridad.
                pass

        received = 0
        response_started = False

        async def limited_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, limited_send)
        except RequestBodyTooLarge:
            # El parseo de multipart consume el body antes de iniciar la
            # respuesta. La guarda evita una segunda respuesta si una app ASGI
            # no estándar hubiese respondido antes de pedir más bytes.
            if not response_started:
                await self._send_413(send)

    @staticmethod
    async def _send_413(send: Send) -> None:
        body = b'{"detail":"El cuerpo de la solicitud excede el limite permitido."}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
