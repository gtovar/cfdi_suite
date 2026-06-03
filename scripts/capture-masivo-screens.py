"""
Captura screenshots de todos los estados faltantes de Análisis Masivo.

Requiere:
  - Frontend corriendo en http://localhost:3000
  - Backend corriendo en http://localhost:8000
  - Google Chrome instalado en /Applications/Google Chrome.app

Uso:
  backend/.venv/bin/python scripts/capture-masivo-screens.py
"""

import time
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, expect

BASE_URL = "http://localhost:3000"
OUT_DIR = Path("docs/screens")
FIXTURES_DIR = Path("src/cfdi/benchmark/fixtures")
AMIGO_DIR = Path("amigo/archivos")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# XMLs válidos (tienen hallazgos → status con_errores)
VALID_XMLS = [
    str(AMIGO_DIR / "factura_ejemplo.xml"),
    str(AMIGO_DIR / "test_centavo_error.xml"),
    str(AMIGO_DIR / "MIN420260228T0029.xml"),
    str(AMIGO_DIR / "MIN420260228T0185.xml"),
    str(AMIGO_DIR / "cfdi-ingresos" / "[I]_[06AAA_71]_197d2952-2a4c-48dd-8906-63d563cd274d.xml"),
    str(AMIGO_DIR / "cfdi-ingresos" / "[I]_[06AAA_71]_a606cc08-26cd-42a5-9960-cc61cbc9df0c.xml"),
]

# XMLs malformados para forzar errores de lectura
ERROR_XMLS = [
    str(FIXTURES_DIR / "malformed-xml.xml"),
    str(FIXTURES_DIR / "missing-comprobante.xml"),
]


def nav_masivo(page: Page):
    """Navega a Análisis Masivo desde cualquier pantalla."""
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    # Click en el nav item "Análisis masivo"
    nav = page.get_by_role("link", name="Análisis masivo").first
    if nav.count() == 0:
        # Fallback: buscar por texto
        page.get_by_text("Análisis masivo").first.click()
    else:
        nav.click()
    page.wait_for_load_state("networkidle")


def upload_files(page: Page, xml_paths: list[str]):
    """Sube XMLs usando el input de archivo oculto."""
    file_input = page.locator('input[type="file"][accept=".xml"]').first
    file_input.set_input_files(xml_paths)


def screenshot(page: Page, name: str):
    path = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  ✓ {path}")


def wait_for_preflight(page: Page, timeout=8000):
    """Espera que aparezca la PreflightCard (datos de archivos seleccionados)."""
    try:
        page.wait_for_selector("text=facturas CFDI detectadas", timeout=timeout)
    except Exception:
        # preflight puede no aparecer si los archivos no son CFDI válidos
        page.wait_for_timeout(1500)


def wait_for_done(page: Page, timeout=60000):
    """Espera que el procesamiento termine (aparece TriageHeader con botones de filtro)."""
    page.wait_for_selector("text=Sin errores", timeout=timeout)
    page.wait_for_timeout(800)  # dejar que las animaciones terminen


def capture_idle_with_preflight(page: Page):
    """Estado: Idle con archivos seleccionados y PreflightCard visible."""
    print("\n[1/6] Capturando masivo-idle-with-preflight...")
    nav_masivo(page)
    upload_files(page, VALID_XMLS[:4])
    wait_for_preflight(page)
    screenshot(page, "masivo-idle-with-preflight")


def capture_processing_start(page: Page):
    """Estado: Inicio del procesamiento (pipeline en paso 2, tabla casi vacía)."""
    print("\n[2/6] Capturando masivo-processing-start...")
    nav_masivo(page)
    upload_files(page, VALID_XMLS)
    wait_for_preflight(page)
    # Click en "Procesar"
    page.get_by_text("Procesar").click()
    # Capturar en los primeros ~400ms (pipeline animando, pocos resultados)
    page.wait_for_timeout(400)
    screenshot(page, "masivo-processing-start")
    # Esperar a que termine antes de continuar
    wait_for_done(page)


def capture_done_filtered_hallazgos(page: Page):
    """Estado: Done con filtro 'Con hallazgos' activo."""
    print("\n[3/6] Capturando masivo-done-filtered-hallazgos...")
    nav_masivo(page)
    upload_files(page, VALID_XMLS)
    wait_for_preflight(page)
    page.get_by_text("Procesar").click()
    wait_for_done(page)
    # Cerrar modal si aparece
    cerrar = page.get_by_role("button", name="Cerrar")
    if cerrar.count() > 0:
        cerrar.first.click()
        page.wait_for_timeout(300)
    # Click en "Con hallazgos" en el TriageHeader
    page.get_by_text("Con hallazgos").first.click()
    page.wait_for_timeout(400)
    screenshot(page, "masivo-done-filtered-hallazgos")


def capture_done_only_errors(page: Page):
    """Estado: Done donde todos los archivos fallaron (solo errores)."""
    print("\n[4/6] Capturando masivo-done-only-errors...")
    nav_masivo(page)
    upload_files(page, ERROR_XMLS)
    wait_for_preflight(page, timeout=3000)
    page.get_by_text("Procesar").click()
    wait_for_done(page, timeout=30000)
    # Cerrar modal si aparece
    cerrar = page.get_by_role("button", name="Cerrar")
    if cerrar.count() > 0:
        cerrar.first.click()
        page.wait_for_timeout(300)
    screenshot(page, "masivo-done-only-errors")


def capture_floating_widget(page: Page):
    """Estado: FloatingBatchWidget visible al navegar a Consultas SAT durante processing."""
    print("\n[5/6] Capturando masivo-floating-widget...")
    nav_masivo(page)
    upload_files(page, VALID_XMLS)
    wait_for_preflight(page)
    page.get_by_text("Procesar").click()
    # Esperar a que haya al menos 1 resultado (widget aparece al navegar)
    page.wait_for_timeout(800)
    # Navegar a Consultas SAT (el widget flotante debe aparecer)
    page.get_by_text("Consultas SAT").first.click()
    page.wait_for_timeout(600)
    screenshot(page, "masivo-floating-widget")
    # Volver a masivo para dejarlo terminar
    page.get_by_text("Análisis masivo").first.click()
    wait_for_done(page)


def capture_inspector_drilldown(page: Page):
    """Estado: Inspector cargado desde fila del Masivo (con botón 'Análisis masivo' de regreso)."""
    print("\n[6/6] Capturando masivo-inspector-drilldown...")
    nav_masivo(page)
    upload_files(page, VALID_XMLS[:4])
    wait_for_preflight(page)
    page.get_by_text("Procesar").click()
    wait_for_done(page)
    # Cerrar modal si aparece
    cerrar = page.get_by_role("button", name="Cerrar")
    if cerrar.count() > 0:
        cerrar.first.click()
        page.wait_for_timeout(300)
    # Click en la primera fila que no sea error (con_errores u ok)
    # Las filas de resultado tienen cursor-pointer
    first_row = page.locator("table tbody tr").first
    first_row.click()
    # Esperar que cargue el inspector (aparece InspectorHeader)
    page.wait_for_timeout(3000)
    screenshot(page, "masivo-inspector-drilldown")


def check_servers():
    import urllib.request
    errors = []
    for url, name in [("http://localhost:3000", "Frontend"), ("http://localhost:8000/api/health", "Backend")]:
        try:
            urllib.request.urlopen(url, timeout=3)
        except Exception:
            errors.append(f"  ✗ {name} no responde en {url}")
    return errors


def main():
    print("=== Captura de pantallas: Análisis Masivo ===\n")

    errors = check_servers()
    if errors:
        print("ERROR: Los servidores no están disponibles:")
        for e in errors:
            print(e)
        print("\nInicia los servidores con:")
        print("  npm run dev        (en una terminal)")
        print("  npm run dev:api    (en otra terminal)")
        sys.exit(1)

    OUT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            headless=False,  # headless=False para ver el progreso; cambiar a True para batch
            args=["--window-size=1400,900"],
        )
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        try:
            capture_idle_with_preflight(page)
            capture_processing_start(page)
            capture_done_filtered_hallazgos(page)
            capture_done_only_errors(page)
            capture_floating_widget(page)
            capture_inspector_drilldown(page)
        except Exception as e:
            print(f"\n✗ Error durante la captura: {e}")
            import traceback
            traceback.print_exc()
            screenshot(page, "error-state")
        finally:
            browser.close()

    print("\n=== Capturas completadas ===")
    print(f"Archivos guardados en: {OUT_DIR}/")


if __name__ == "__main__":
    main()
