from __future__ import annotations

import asyncio
import hashlib
import os
import unittest
from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.app.rate_limits import rate_limit
from backend.app.routers.pdf import batch_progress, pdf_progress
from backend.app.security import verify_user_identity


def _test_app() -> FastAPI:
    app = FastAPI(dependencies=[Depends(verify_user_identity)])

    @app.get("/api/cfdi/pdf/{job_id}/progress")
    async def progress(_rate=rate_limit(2)):
        return {"ok": True}

    @app.post("/api/test")
    async def post_test():
        return {"ok": True}

    @app.get("/api/not-listed")
    async def not_listed():
        return {"ok": True}

    return app


class QueryAuthenticationAndRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"API_BEARER_TOKEN": "test-secret"})
        self.env.start()
        self.client = TestClient(_test_app())

    def tearDown(self):
        self.env.stop()

    def test_query_token_uses_the_same_rate_limit_fingerprint(self):
        statuses = [
            self.client.get("/api/cfdi/pdf/job/progress?token=test-secret").status_code
            for _ in range(4)
        ]
        self.assertEqual(statuses, [200, 200, 429, 429])

    def test_query_token_is_rejected_for_post_and_non_listed_get(self):
        self.assertEqual(self.client.post("/api/test?token=test-secret").status_code, 401)
        self.assertEqual(self.client.get("/api/not-listed?token=test-secret").status_code, 401)

    def test_query_token_is_limited_to_the_sse_and_batch_download_allowlist(self):
        for path in (
            "/api/cfdi/pdf/job/progress",
            "/api/cfdi/pdf/batch/batch/progress",
            "/api/cfdi/pdf/batch/batch/download",
        ):
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": path,
                    "query_string": b"token=test-secret",
                    "headers": [],
                }
            )
            self.assertEqual(asyncio.run(verify_user_identity(request)), "default-tenant")

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/cfdi/pdf/job/download",
                "query_string": b"token=test-secret",
                "headers": [],
            }
        )
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(verify_user_identity(request))
        self.assertEqual(raised.exception.status_code, 401)

    def test_authorization_header_remains_effective_with_capability_token_query(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/sat/enquiry/batch/result",
            "query_string": b"token=download-capability",
            "headers": [(b"authorization", b"Bearer test-secret")],
        }
        request = Request(scope)
        self.assertEqual(asyncio.run(verify_user_identity(request)), "default-tenant")
        self.assertTrue(request.state.auth_fingerprint)

    def test_identity_and_fingerprint_are_cached_on_the_request(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/cfdi/pdf/job/progress",
            "query_string": b"token=test-secret",
            "headers": [],
        }
        request = Request(scope)
        with patch("backend.app.security.sha256", wraps=hashlib.sha256) as digest:
            self.assertEqual(asyncio.run(verify_user_identity(request)), "default-tenant")
            self.assertEqual(asyncio.run(verify_user_identity(request)), "default-tenant")
        self.assertEqual(digest.call_count, 1)

    def test_pdf_sse_responses_do_not_cache_or_send_referrers(self):
        for response in (
            asyncio.run(pdf_progress("job")),
            asyncio.run(batch_progress("batch")),
        ):
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["referrer-policy"], "no-referrer")
            self.assertEqual(response.headers["x-accel-buffering"], "no")
