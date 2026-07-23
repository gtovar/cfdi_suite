"""
cpu_quota.py — Cuota real de CPU del contenedor, leída de cgroups.

Extraído de pdf_pipeline.py (2026-07-22, tras un code review) — vivía ahí, pero
pdf_pipeline.py se declara a sí mismo "orquestador de las tres capas XML→PDF",
no un módulo de introspección de sistema. Mismo patrón de nombre angosto que
gcs_range_auth.py (no un "utils.py" genérico — este proyecto no tiene ese
precedente).

NO usa multiprocessing.cpu_count(), que solo reporta afinidad (en cuántos
núcleos puede correr el proceso), un mecanismo de Linux distinto e
independiente de la cuota de tiempo de CPU que Cloud Run factura y limita.
Confirmado en vivo 2026-07-22 con un Job de diagnóstico desechable: en una
instancia con --cpu=2 configurado, cpu_count() reportaba 4 (afinidad de la
máquina física de abajo), mientras que la cuota real de cgroups
(cpu.cfs_quota_us / cpu.cfs_period_us, cgroup v1 — Cloud Run no usa v2) dio
161200/100000 = 1.612, que redondea a 2 — coincide con lo medido con una
prueba de carga real (curl concurrente contra /internal/generate-pdf: solo
~2 peticiones corren a velocidad normal a la vez por instancia).
"""
from __future__ import annotations

# Techo estático de seguridad, independiente de si el valor final viene de la
# autodetección o de un override manual (PDF_POOL_WORKERS puesto a mano) —
# mismo valor que el viejo min(8, cpu_count()) que este módulo reemplaza.
# Cada worker es un proceso completo con WeasyPrint/reportlab/lxml cargados;
# sin este techo, un valor grande (autodetectado en un ambiente futuro con
# más CPU, o un typo humano) puede agotar la memoria del contenedor.
MAX_POOL_WORKERS = 8


def detect_real_cpu_quota() -> float | None:
    """Lee la cuota REAL de CPU directo de cgroups (v2 primero, cae a v1).

    Devuelve None si no se puede leer o si no hay límite configurado (quota
    "max"/-1) — en ese caso el llamador debe caer a un valor por defecto
    conservador, no asumir cómputo ilimitado.

    Atrapa OSError (no excepciones específicas una por una) porque ya se nos
    olvidó una vez: la rama v1 original atrapaba ZeroDivisionError y la v2 no,
    pese a hacer la misma división — y ninguna de las dos atrapaba
    PermissionError, real en entornos con sandboxing más restrictivo que
    Cloud Run (CI, contenedores rootless). OSError es la clase padre de
    FileNotFoundError/PermissionError/IsADirectoryError — no depende de
    enumerar bien cada caso.
    """
    try:
        with open("/sys/fs/cgroup/cpu.max") as f:  # cgroup v2
            max_str, period_str = f.read().split()
            if max_str == "max":
                return None
            return int(max_str) / int(period_str)
    except (OSError, ValueError, ZeroDivisionError):
        pass
    try:
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as f:  # cgroup v1 (Cloud Run)
            quota = int(f.read().strip())
        if quota <= 0:
            return None
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as f:
            period = int(f.read().strip())
        return quota / period
    except (OSError, ValueError, ZeroDivisionError):
        return None


def default_pool_workers() -> int:
    """Cuántos procesos reales caben aquí, con techo de seguridad aplicado."""
    quota = detect_real_cpu_quota()
    if quota and quota > 0:
        workers = max(1, round(quota))
    else:
        workers = 2  # respaldo conservador si cgroups no es legible
    return min(MAX_POOL_WORKERS, workers)
