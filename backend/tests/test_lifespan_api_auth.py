"""Startup guard for the production API authentication configuration."""

import os
import unittest
from unittest.mock import patch

from backend.app.main import _lifespan, app


class TestLifespanApiAuth(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_rejects_production_without_api_bearer_token(self):
        with patch.dict(
            os.environ,
            {"REQUIRE_API_AUTH": "true"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "API_BEARER_TOKEN"):
                async with _lifespan(app):
                    pass

    async def test_lifespan_allows_production_with_api_bearer_token(self):
        with patch.dict(
            os.environ,
            {
                "REQUIRE_API_AUTH": "true",
                "API_BEARER_TOKEN": "test-secret",
            },
            clear=True,
        ):
            async with _lifespan(app):
                pass

    async def test_lifespan_allows_local_development_without_auth_flag(self):
        with patch.dict(os.environ, {}, clear=True):
            async with _lifespan(app):
                pass
