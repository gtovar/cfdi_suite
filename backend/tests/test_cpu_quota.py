"""
Tests de cpu_quota.py — autodetección de cuota real de CPU vía cgroups.

Cubre los hallazgos reales de un code review (2026-07-22): asimetría de manejo
de excepciones entre las ramas cgroup v2/v1, PermissionError no atrapado, y el
techo de seguridad (MAX_POOL_WORKERS) aplicado tanto a la autodetección como al
override manual en pdf_pipeline.py.
"""
from __future__ import annotations

import builtins
from unittest.mock import mock_open, patch

import pytest

from backend.app.services import cpu_quota


def _open_side_effect(existing: dict[str, str]):
    """Simula el sistema de archivos: solo las rutas en `existing` "existen",
    devolviendo su contenido; cualquier otra ruta lanza FileNotFoundError, igual
    que el open() real en una máquina sin ese archivo."""
    real_open = builtins.open

    def _fake_open(path, *args, **kwargs):
        if path in existing:
            return mock_open(read_data=existing[path])(path, *args, **kwargs)
        raise FileNotFoundError(path)

    return _fake_open


class TestDetectRealCpuQuota:
    def test_cgroup_v2_present_returns_quota(self):
        fs = {"/sys/fs/cgroup/cpu.max": "200000 100000\n"}
        with patch("builtins.open", side_effect=_open_side_effect(fs)):
            assert cpu_quota.detect_real_cpu_quota() == 2.0

    def test_cgroup_v2_max_means_unlimited_returns_none(self):
        fs = {"/sys/fs/cgroup/cpu.max": "max 100000\n"}
        with patch("builtins.open", side_effect=_open_side_effect(fs)):
            assert cpu_quota.detect_real_cpu_quota() is None

    def test_cgroup_v1_present_returns_quota(self):
        # El caso real medido en vivo 2026-07-22: --cpu=2 -> 161200/100000 = 1.612
        fs = {
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "161200\n",
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000\n",
        }
        with patch("builtins.open", side_effect=_open_side_effect(fs)):
            assert cpu_quota.detect_real_cpu_quota() == pytest.approx(1.612)

    def test_cgroup_v1_quota_unlimited_negative_one_returns_none(self):
        fs = {"/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "-1\n"}
        with patch("builtins.open", side_effect=_open_side_effect(fs)):
            assert cpu_quota.detect_real_cpu_quota() is None

    def test_no_cgroup_files_at_all_returns_none_not_raises(self):
        # El caso real en Mac/desarrollo local: ninguna ruta existe.
        with patch("builtins.open", side_effect=_open_side_effect({})):
            assert cpu_quota.detect_real_cpu_quota() is None

    def test_v2_zero_period_does_not_raise_zerodivisionerror(self):
        # Hallazgo del review: la rama v2 original no atrapaba ZeroDivisionError
        # pese a hacer la misma división que v1 (que sí lo atrapaba).
        fs = {"/sys/fs/cgroup/cpu.max": "200000 0\n"}
        with patch("builtins.open", side_effect=_open_side_effect(fs)):
            assert cpu_quota.detect_real_cpu_quota() is None

    def test_v1_zero_period_does_not_raise_zerodivisionerror(self):
        fs = {
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "161200\n",
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "0\n",
        }
        with patch("builtins.open", side_effect=_open_side_effect(fs)):
            assert cpu_quota.detect_real_cpu_quota() is None

    def test_permission_error_on_v2_falls_back_to_v1_not_raises(self):
        # Hallazgo del review: ni v2 ni v1 atrapaban PermissionError -- un
        # entorno con sandboxing más estricto que Cloud Run (CI, contenedor
        # rootless) podía tronar el import completo del módulo.
        def _raises_permission(path, *args, **kwargs):
            if path == "/sys/fs/cgroup/cpu.max":
                raise PermissionError(path)
            raise FileNotFoundError(path)

        with patch("builtins.open", side_effect=_raises_permission):
            assert cpu_quota.detect_real_cpu_quota() is None

    def test_permission_error_on_v1_returns_none_not_raises(self):
        def _raises_permission(path, *args, **kwargs):
            raise PermissionError(path)

        with patch("builtins.open", side_effect=_raises_permission):
            assert cpu_quota.detect_real_cpu_quota() is None


class TestDefaultPoolWorkers:
    def test_rounds_detected_quota(self):
        with patch.object(cpu_quota, "detect_real_cpu_quota", return_value=1.612):
            assert cpu_quota.default_pool_workers() == 2

    def test_falls_back_to_two_when_quota_undetectable(self):
        with patch.object(cpu_quota, "detect_real_cpu_quota", return_value=None):
            assert cpu_quota.default_pool_workers() == 2

    def test_never_returns_zero_for_tiny_quota(self):
        with patch.object(cpu_quota, "detect_real_cpu_quota", return_value=0.1):
            assert cpu_quota.default_pool_workers() == 1

    def test_clamps_large_quota_to_max_pool_workers(self):
        # Techo de seguridad (Hallazgo 5 del review): un ambiente futuro con
        # mucha más CPU no debe poder levantar procesos sin límite.
        with patch.object(cpu_quota, "detect_real_cpu_quota", return_value=64.0):
            assert cpu_quota.default_pool_workers() == cpu_quota.MAX_POOL_WORKERS


class TestPdfPoolWorkersEnvParsing:
    """Prueba el parseo blindado en pdf_pipeline.py -- se prueba importando el
    módulo con distintos valores de PDF_POOL_WORKERS en el entorno, porque la
    lógica corre a nivel de módulo (Hallazgos 1 y 6 del review)."""

    def _reimport_with_env(self, monkeypatch, env_value):
        import importlib
        from backend.app.services import pdf_pipeline as module

        if env_value is None:
            monkeypatch.delenv("PDF_POOL_WORKERS", raising=False)
        else:
            monkeypatch.setenv("PDF_POOL_WORKERS", env_value)
        return importlib.reload(module)

    def test_empty_string_env_var_does_not_crash_falls_back_to_autodetect(self, monkeypatch):
        with patch.object(cpu_quota, "detect_real_cpu_quota", return_value=None):
            module = self._reimport_with_env(monkeypatch, "")
        assert module.PDF_POOL_WORKERS == 2  # respaldo, no crashea

    def test_non_numeric_env_var_does_not_crash_falls_back_to_autodetect(self, monkeypatch):
        with patch.object(cpu_quota, "detect_real_cpu_quota", return_value=None):
            module = self._reimport_with_env(monkeypatch, "not-a-number")
        assert module.PDF_POOL_WORKERS == 2

    def test_large_manual_override_is_clamped_to_max(self, monkeypatch):
        module = self._reimport_with_env(monkeypatch, "999")
        assert module.PDF_POOL_WORKERS == module.MAX_POOL_WORKERS

    def test_valid_small_override_is_respected(self, monkeypatch):
        module = self._reimport_with_env(monkeypatch, "3")
        assert module.PDF_POOL_WORKERS == 3

    def test_zero_or_negative_override_is_clamped_to_one(self, monkeypatch):
        module = self._reimport_with_env(monkeypatch, "0")
        assert module.PDF_POOL_WORKERS == 1
