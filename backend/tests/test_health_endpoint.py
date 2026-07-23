"""
Test de /api/health -- Paso 6 de
docs/plan-implementacion-resiliencia-redis-2026-07-23.md. Restricción
crítica: este endpoint NUNCA debe hacer una llamada real a Redis (el
presupuesto de cuota son ~11 peticiones/min), solo leer la bandera en
memoria de redis_safety.is_degraded().
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import redis_safety


class HealthEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        redis_safety._degraded_until = 0.0

    def tearDown(self) -> None:
        redis_safety._degraded_until = 0.0

    def test_status_ok_sin_degradacion(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_status_degraded_cuando_la_bandera_esta_activa(self) -> None:
        redis_safety.mark_degraded()
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "degraded", "realtime": "unavailable"})

    def test_no_hace_ninguna_llamada_real_a_redis(self) -> None:
        """health() solo debe leer redis_safety.is_degraded() (memoria) --
        nunca instanciar ni llamar al cliente de Redis directamente."""
        with patch("backend.app.services.redis_safety.is_degraded") as mock_is_degraded:
            mock_is_degraded.return_value = False
            response = self.client.get("/api/health")

        mock_is_degraded.assert_called_once_with()
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
