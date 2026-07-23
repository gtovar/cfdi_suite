"""
Tests de redis_errors.is_redis_quota_error y redis_safety.safe_redis_call/
is_degraded -- post-incidente 2026-07-23 (cuota de Upstash agotada, ver
docs/mesa-decision-resiliencia-redis-2026-07-23.md). Ver "Plan de pruebas" en
docs/plan-implementacion-resiliencia-redis-2026-07-23.md para los casos
mínimos exigidos.
"""
from __future__ import annotations

import asyncio
import time
import unittest

from backend.app.services import redis_safety
from backend.app.services.redis_errors import is_redis_quota_error


def _run(coro):
    return asyncio.run(coro)


class IsRedisQuotaErrorTests(unittest.TestCase):
    def test_reconoce_el_mensaje_real_del_incidente(self) -> None:
        exc = Exception(
            "max requests limit exceeded. Limit: 500000, Usage: 500000. "
            "See https://upstash.com/docs/redis/troubleshooting/max_requests_limit for details"
        )
        self.assertTrue(is_redis_quota_error(exc))

    def test_reconoce_variantes_conocidas(self) -> None:
        self.assertTrue(is_redis_quota_error(Exception("Max daily request limit reached")))
        self.assertTrue(is_redis_quota_error(Exception("MAX_REQUESTS_LIMIT")))

    def test_no_reconoce_excepciones_no_relacionadas(self) -> None:
        self.assertFalse(is_redis_quota_error(ConnectionError("connection refused")))
        self.assertFalse(is_redis_quota_error(TimeoutError("timed out")))
        self.assertFalse(is_redis_quota_error(ValueError("algo distinto")))


class SafeRedisCallTests(unittest.TestCase):
    def setUp(self) -> None:
        # Aislar el estado global de _degraded_until entre tests.
        redis_safety._degraded_until = 0.0

    def test_nunca_propaga_y_devuelve_none_en_error(self) -> None:
        async def boom():
            raise ConnectionError("boom")

        result = _run(redis_safety.safe_redis_call(boom))
        self.assertIsNone(result)

    def test_devuelve_el_valor_real_cuando_no_hay_error(self) -> None:
        async def ok():
            return "valor"

        result = _run(redis_safety.safe_redis_call(ok))
        self.assertEqual(result, "valor")

    def test_activa_degradado_solo_ante_error_de_cuota_real(self) -> None:
        async def quota_error():
            raise Exception("max requests limit exceeded. Limit: 500000, Usage: 500000.")

        self.assertFalse(redis_safety.is_degraded())
        _run(redis_safety.safe_redis_call(quota_error))
        self.assertTrue(redis_safety.is_degraded())

    def test_no_activa_degradado_ante_error_no_relacionado(self) -> None:
        async def other_error():
            raise ConnectionError("connection refused")

        _run(redis_safety.safe_redis_call(other_error))
        self.assertFalse(redis_safety.is_degraded())

    def test_is_degraded_expira_tras_el_cooldown(self) -> None:
        redis_safety.mark_degraded()
        self.assertTrue(redis_safety.is_degraded())
        # Simula que el cooldown ya pasó sin dormir de verdad en el test.
        redis_safety._degraded_until = time.monotonic() - 1
        self.assertFalse(redis_safety.is_degraded())


if __name__ == "__main__":
    unittest.main()
