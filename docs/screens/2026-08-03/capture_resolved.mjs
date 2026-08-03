/**
 * Captura del estado RESUELTO de la tabla de Analisis masivo.
 *
 * El backend local no puede subir a GCS (falta proyecto/credenciales) y no quiero
 * escribir en el bucket de produccion. Asi que intercepto los 4 endpoints del flujo
 * durable con page.route() y sirvo resultados sinteticos progresivos.
 * El render es 100% del cliente: lo que se ve es el componente real.
 *
 * Contrato replicado de:
 *   BatchAnalysisPage.tsx:990  POST /api/cfdi/batch/loose-batches
 *   BatchAnalysisPage.tsx:1019 POST .../files/:jobId
 *   BatchAnalysisPage.tsx:918  POST /api/cfdi/batch/:id/start
 *   BatchAnalysisPage.tsx:897  GET  /api/cfdi/batch/status/:id
 *   BatchFileResult en src/lib/batch-api-client.ts:4
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const require = createRequire('/Users/gil/Documents/cfdi_suite/frontend/package.json');
const { chromium } = require('playwright');

const SCRATCH = '/private/tmp/claude-501/-Users-gil-Documents-cfdi-suite/9eca0c2f-902a-49d5-a9e6-2846a1933fb4/scratchpad';
const OUT = path.join(SCRATCH, 'shots');
const BULK = path.join(SCRATCH, 'bulk_xml');
const BASE = 'http://localhost:3000';
const BATCH_ID = '3f2a9c14-7b6d-4e58-9a01-c5d8e6f41b27';

// Datos variados a proposito: emisores distintos, montos de distinta magnitud,
// fechas dispersas, mezcla de estados. La captura de junio repetia el mismo
// emisor en todas las filas y eso falseaba el juicio de diseno.
const EMISORES = [
  ['AAA010101AAA', 'AUCHAN COMERCIALIZADORA MEXICANA SA DE CV'],
  ['GTO920115H45', 'GRUPO TORRES OCAMPO'],
  ['SEM8801019P3', 'SERVICIOS EMPRESARIALES DEL BAJIO SA DE CV'],
  ['MIN420228T00', 'MINERA INDUSTRIAL DEL NORTE SAPI DE CV'],
  ['PCO150612QX8', 'PAPELERIA Y CONSUMIBLES DE OCCIDENTE'],
  ['LOM770304RT2', 'LOGISTICA MULTIMODAL LOMA SA DE CV'],
  ['CFE370814QI0', 'COMISION FEDERAL DE ELECTRICIDAD'],
  ['XAXX010101000', 'PUBLICO EN GENERAL'],
];
const TOTALES = ['117.99', '683.14', '1250.00', '48920.55', '9.99', '235000.00', '3480.25', '76.40', '15999.90', '2.50'];
const FECHAS = ['2026-04-15', '2026-05-30', '2026-04-28', '2026-01-09', '2026-06-02', '2026-03-17', '2026-05-11', '2026-02-24'];

function listFiles() {
  return fs.readdirSync(BULK).filter((f) => f.endsWith('.xml')).sort().map((f) => path.join(BULK, f));
}

function makeResult(filename, i) {
  // ~1 de cada 9 falla, ~1 de cada 3 trae hallazgos
  if (i % 9 === 8) {
    return { filename, status: 'error', profile: 'unknown', rfc_emisor: '', rfc_receptor: '',
      nombre_emisor: '', total: '', fecha: '', findings_count: 0,
      error: 'XML mal formado: no se encontro el nodo cfdi:Comprobante' };
  }
  const [rfc, nombre] = EMISORES[i % EMISORES.length];
  const conHallazgos = i % 3 === 1;
  return {
    filename,
    status: conHallazgos ? 'con_errores' : 'ok',
    profile: i % 5 === 4 ? 'pagos' : 'ingreso',
    rfc_emisor: rfc,
    rfc_receptor: 'MFI0908114P8',
    nombre_emisor: nombre,
    total: TOTALES[i % TOTALES.length],
    fecha: FECHAS[i % FECHAS.length],
    findings_count: conHallazgos ? (i % 4) + 1 : 0,
    error: null,
  };
}

fs.mkdirSync(OUT, { recursive: true });
const shot = async (page, name, full = false) => {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: full });
  console.log(`  OK ${name}.png`);
};
async function shotTable(page, name) {
  try {
    const el = page.locator('table').first();
    if (await el.count()) {
      const c = el.locator("xpath=ancestor::div[contains(@class,'rounded-xl')][1]");
      await ((await c.count()) ? c.first() : el).screenshot({ path: path.join(OUT, `${name}.png`), timeout: 8000 });
      console.log(`  OK ${name}.png (crop)`);
      return;
    }
  } catch (e) { console.log(`  !! crop fallo ${name}`); }
  await shot(page, name);
}

const files = listFiles();
console.log(`${files.length} XMLs`);
const names = files.map((f) => path.basename(f));

let resolvedCount = 0; // lo controlo yo desde el script, no por reloj

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1512, height: 950 }, deviceScaleFactor: 2 });
await ctx.addInitScript(() => { try { localStorage.setItem('cfdi-suite-auth-token', 'dev-local-token'); } catch (e) {} });

// --- interceptores ---
await ctx.route('**/api/cfdi/batch/loose-batches', async (route) => {
  const body = JSON.parse(route.request().postData() || '{}');
  const jobs = (body.files || []).map((f, i) => ({
    jobId: `job-${String(i).padStart(4, '0')}`, filename: f.filename, size: f.size,
  }));
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ batchId: BATCH_ID, jobs }) });
});
await ctx.route('**/api/cfdi/batch/loose-batches/*/files/*', (route) =>
  route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
await ctx.route('**/api/cfdi/batch/*/start', (route) =>
  route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
await ctx.route('**/api/cfdi/batch/status/*', async (route) => {
  const total = names.length;
  const n = Math.min(resolvedCount, total);
  const results = names.slice(0, n).map((fn, i) => makeResult(fn, i));
  const done = results.filter((r) => r.status !== 'error').length;
  const error = results.filter((r) => r.status === 'error').length;
  await route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      status: n >= total ? 'done' : 'processing',
      results, total, pending: total - n, processing: n >= total ? 0 : 4, done, error,
      upload: { total, uploaded: total, awaitingUpload: 0 },
    }),
  });
});
await ctx.route('**/api/pusher/**', (route) => route.fulfill({ status: 503, body: '{}' }));

const page = await ctx.newPage();
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1800);
await page.getByText('Análisis masivo', { exact: false }).first().click();
await page.waitForTimeout(800);
await page.locator('input[type="file"][accept=".xml"]').first().setInputFiles(files);
await page.waitForSelector('text=facturas CFDI detectadas', { timeout: 12000 }).catch(() => page.waitForTimeout(2500));
await page.getByText('Procesar', { exact: false }).first().click();

// Estado MIXTO: parte resuelto, parte skeleton — es lo que el usuario ve la mayor parte del tiempo
resolvedCount = 6;
await page.waitForTimeout(4000);
await shot(page, 'R1-mixto-viewport');
await shotTable(page, 'R2-mixto-tabla');

resolvedCount = 18;
await page.waitForTimeout(4000);
await shot(page, 'R3-mixto-avanzado-viewport');
await shotTable(page, 'R4-mixto-avanzado-tabla');

// Estado RESUELTO COMPLETO
resolvedCount = names.length;
await page.waitForTimeout(5000);
await shot(page, 'R5-resuelto-viewport');
const cerrar = page.getByRole('button', { name: 'Cerrar' });
if (await cerrar.count()) { await cerrar.first().click(); await page.waitForTimeout(600); }
await shot(page, 'R6-resuelto-sin-modal');
await shotTable(page, 'R7-resuelto-tabla');
await shot(page, 'R8-resuelto-fullpage', true);

// scroll dentro de la tabla, para ver si los ultimos registros son alcanzables
try {
  const cont = page.locator('table').first().locator("xpath=ancestor::div[contains(@class,'overflow-auto')][1]");
  await cont.first().evaluate((el) => { el.scrollTop = el.scrollHeight; });
  await page.waitForTimeout(600);
  await shotTable(page, 'R9-resuelto-scroll-fondo');
} catch (e) { console.log('  !! scroll fallo'); }

await browser.close();
console.log('\nListo ->', OUT);
