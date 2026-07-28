from __future__ import annotations

import asyncio
import io
import unittest

from fastapi import HTTPException, UploadFile

from backend.app.middleware import (
    FIEL_TOTAL_MAX_BYTES,
    MULTIPART_OVERHEAD_BYTES,
    PDF_SINGLE_XML_MAX_BYTES,
    REQUEST_BODY_LIMITS,
    RouteBodySizeLimitMiddleware,
    SAT_XLSX_MAX_BYTES,
)
from backend.app.routers.batch import _read_upload_limited
from backend.app.routers.rfc_validation import _read_fiel_upload
from backend.app.routers.sat_enquiry import _read_xlsx_upload
from backend.app.services.batch_reports import generate_diot


def _run(coro):
    return asyncio.run(coro)


async def _invoke(middleware, messages):
    sent = []

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await middleware(
        {"type": "http", "path": "/upload", "headers": []}, receive, send
    )
    return sent


class RouteBodySizeLimitMiddlewareTests(unittest.TestCase):
    def test_rejects_content_length_before_calling_application(self):
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        middleware = RouteBodySizeLimitMiddleware(app, {"/upload": 10})
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"x"}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "path": "/upload", "headers": [(b"content-length", b"11")]}
        _run(middleware(scope, receive, send))
        self.assertFalse(called)
        self.assertEqual(sent[-2]["status"], 413)

    def test_rejects_stream_without_content_length_when_accumulated_limit_is_crossed(self):
        received_by_app = []

        async def app(scope, receive, send):
            while True:
                message = await receive()
                received_by_app.append(message)
                if not message.get("more_body"):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})

        middleware = RouteBodySizeLimitMiddleware(app, {"/upload": 10})
        sent = _run(_invoke(middleware, [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"78901", "more_body": False},
        ]))

        self.assertEqual(len(received_by_app), 1)
        self.assertEqual(sent[0]["status"], 413)

    def test_allows_a_stream_at_the_exact_limit(self):
        async def app(scope, receive, send):
            while (message := await receive()).get("more_body"):
                pass
            await send({"type": "http.response.start", "status": 204, "headers": []})

        middleware = RouteBodySizeLimitMiddleware(app, {"/upload": 10})
        sent = _run(_invoke(middleware, [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"67890", "more_body": False},
        ]))
        self.assertEqual(sent[0]["status"], 204)


class BatchChunkReadersTests(unittest.TestCase):
    def test_route_limits_keep_50mb_analysis_and_cover_xlsx_and_fiel(self):
        self.assertEqual(
            REQUEST_BODY_LIMITS["/api/cfdi/analyze"],
            PDF_SINGLE_XML_MAX_BYTES + MULTIPART_OVERHEAD_BYTES,
        )
        self.assertEqual(
            REQUEST_BODY_LIMITS["/api/sat/enquiry/batch"],
            SAT_XLSX_MAX_BYTES + MULTIPART_OVERHEAD_BYTES,
        )
        self.assertEqual(
            REQUEST_BODY_LIMITS["/api/fiel/configure"],
            FIEL_TOTAL_MAX_BYTES + MULTIPART_OVERHEAD_BYTES,
        )

    def test_reader_enforces_the_aggregate_budget_across_files(self):
        upload = UploadFile(filename="factura.xml", file=io.BytesIO(b"<cfdi/>"))
        with self.assertRaisesRegex(HTTPException, "límite agregado"):
            _run(_read_upload_limited(upload, total_bytes=100 * 1024 * 1024))

    def test_diot_accepts_a_one_pass_iterable_with_the_same_result(self):
        xml = (
            b'<Comprobante><Emisor Rfc="XAXX010101000"/><Receptor Rfc="XAXX010101000"/>'
            b'<Traslado Impuesto="002" TasaOCuota="0.160000" Base="100.00"/></Comprobante>'
        )
        expected = generate_diot([xml], year=2026, month=1)
        self.assertEqual(expected, generate_diot(iter([xml]), year=2026, month=1))

    def test_xlsx_and_fiel_readers_reject_when_their_budgets_are_exceeded(self):
        oversized_xlsx = UploadFile(
            filename="lote.xlsx", file=io.BytesIO(b"x" * (SAT_XLSX_MAX_BYTES + 1))
        )
        with self.assertRaises(HTTPException) as xlsx_error:
            _run(_read_xlsx_upload(oversized_xlsx))
        self.assertEqual(xlsx_error.exception.status_code, 413)

        oversized_key = UploadFile(
            filename="firma.key", file=io.BytesIO(b"x" * (FIEL_TOTAL_MAX_BYTES + 1))
        )
        with self.assertRaises(HTTPException) as fiel_error:
            _run(_read_fiel_upload(oversized_key, total_bytes=0))
        self.assertEqual(fiel_error.exception.status_code, 413)
