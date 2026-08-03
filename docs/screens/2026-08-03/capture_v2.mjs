/**
 * Captura dirigida de la tabla de progreso/resultados (Analisis masivo + Conversion masiva).
 * Valida 3 quejas concretas:
 *   Q1 "los ultimos registros no se ven, se quedan escondidos"  -> lote grande + scroll al fondo
 *   Q2 "algunas columnas deberian estar centradas"              -> crops de la tabla
 *   Q3 "cuando cambia de spinning a otra etiqueta se ve mal"    -> rafaga de frames en la transicion
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const require = createRequire('/Users/gil/Documents/cfdi_suite/frontend/package.json');
const { chromium } = require('playwright');

const ROOT = '/Users/gil/Documents/cfdi_suite';
const SCRATCH = '/private/tmp/claude-501/-Users-gil-Documents-cfdi-suite/9eca0c2f-902a-49d5-a9e6-2846a1933fb4/scratchpad';
const OUT = path.join(SCRATCH, 'shots');
const BULK = path.join(SCRATCH, 'bulk_xml');
const FIX = path.join(ROOT, 'frontend/src/cfdi/benchmark/fixtures');
const BASE = 'http://localhost:3000';

const AMIGO = '/Users/gil/Documents/cfdi-suite-extras/amigo/archivos';
const BROKEN = ['malformed-xml', 'missing-comprobante'];

function walk(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (e.name.toLowerCase().endsWith('.xml')) out.push(p);
  }
  return out;
}

/** XMLs REALES del archivo del usuario + 2 rotos para forzar el estado de error. */
function buildBulk(n = 45) {
  fs.rmSync(BULK, { recursive: true, force: true });
  fs.mkdirSync(BULK, { recursive: true });
  const real = walk(AMIGO).sort();
  console.log(`  ${real.length} XMLs reales disponibles en amigo/archivos`);
  const picked = real.slice(0, n - 2);
  const out = [];
  for (const src of picked) {
    const dst = path.join(BULK, path.basename(src));
    fs.copyFileSync(src, dst);
    out.push(dst);
  }
  for (const b of BROKEN) {
    const dst = path.join(BULK, `${b}.xml`);
    fs.copyFileSync(path.join(FIX, `${b}.xml`), dst);
    out.push(dst);
  }
  return out;
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
      const container = el.locator("xpath=ancestor::div[contains(@class,'rounded-xl')][1]");
      const target = (await container.count()) ? container.first() : el;
      await target.screenshot({ path: path.join(OUT, `${name}.png`) });
      console.log(`  OK ${name}.png (crop tabla)`);
      return;
    }
  } catch (e) { console.log(`  !! crop fallo ${name}: ${e.message.split('\n')[0]}`); }
  await shot(page, name);
}

async function goTo(page, label) {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  // networkidle nunca llega: la app hace polling continuo del batch
  await page.waitForTimeout(1800);
  await page.getByText(label, { exact: false }).first().click();
  await page.waitForTimeout(900);
}

async function scrollBottom(page, name) {
  try {
    const cont = page.locator('table').first().locator("xpath=ancestor::div[contains(@class,'overflow-auto')][1]");
    await cont.first().evaluate((el) => { el.scrollTop = el.scrollHeight; });
    await page.waitForTimeout(500);
    await shotTable(page, name);
  } catch (e) { console.log('  !! scroll fallo:', e.message.split('\n')[0]); }
}

async function masivo(page, files) {
  console.log(`\n[ANALISIS MASIVO] ${files.length} archivos`);
  await goTo(page, 'Análisis masivo');
  await page.locator('input[type="file"][accept=".xml"]').first().setInputFiles(files);
  await page.waitForSelector('text=facturas CFDI detectadas', { timeout: 12000 }).catch(() => page.waitForTimeout(2500));
  await shot(page, '01-masivo-idle-preflight');

  await page.getByText('Procesar', { exact: false }).first().click();

  // Q3: transicion skeleton -> badge
  const marks = [250, 600, 1000, 1600];
  let prev = 0;
  for (const ms of marks) {
    await page.waitForTimeout(ms - prev); prev = ms;
    await shotTable(page, `02-masivo-transicion-${ms}ms`);
  }

  // Q1: durante proceso
  await page.waitForTimeout(1200);
  await shot(page, '03-masivo-processing-viewport');
  await scrollBottom(page, '04-masivo-scrolled-al-fondo');

  await page.waitForSelector('text=Sin errores', { timeout: 180000 }).catch(() => console.log('  !! no llego a done'));
  await page.waitForTimeout(1200);
  await shot(page, '05-masivo-done-viewport');
  const cerrar = page.getByRole('button', { name: 'Cerrar' });
  if (await cerrar.count()) { await cerrar.first().click(); await page.waitForTimeout(500); }
  await shot(page, '06-masivo-done-sin-modal');
  await shotTable(page, '07-masivo-done-tabla-crop');
  await scrollBottom(page, '08-masivo-done-scrolled');
  await shot(page, '09-masivo-done-fullpage', true);
}

async function conversion(page, files) {
  console.log(`\n[CONVERSION MASIVA] ${files.length} archivos`);
  await goTo(page, 'Conversión masiva');
  await page.locator('input[type="file"]').first().setInputFiles(files);
  await page.waitForTimeout(1500);
  await shot(page, '10-conversion-idle-viewport');
  await shotTable(page, '11-conversion-idle-tabla-crop');

  const btn = page.getByText('Iniciar conversión masiva', { exact: false });
  if (!(await btn.count())) { console.log('  !! sin boton de iniciar'); return; }
  await btn.first().click();
  const marks = [500, 1200, 2500, 4500];
  let prev = 0;
  for (const ms of marks) {
    await page.waitForTimeout(ms - prev); prev = ms;
    await shotTable(page, `12-conversion-processing-${ms}ms`);
  }
  await shot(page, '13-conversion-processing-viewport');
  await scrollBottom(page, '14-conversion-scrolled-al-fondo');
  await page.waitForTimeout(6000);
  await shot(page, '15-conversion-later-viewport');
}

const files = buildBulk(45);
console.log(`Generados ${files.length} XMLs`);
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1512, height: 950 }, deviceScaleFactor: 2 });
await ctx.addInitScript(() => { try { localStorage.setItem('cfdi-suite-auth-token', 'dev-local-token'); } catch (e) {} });
const page = await ctx.newPage();
page.on('console', (m) => { if (m.type() === 'error') console.log('  [console error]', m.text().slice(0, 160)); });
try { await masivo(page, files); } catch (e) { console.log('ERROR masivo:', e.message.split('\n')[0]); await shot(page, 'ERR-masivo'); }
try { await conversion(page, files.slice(0, 20)); } catch (e) { console.log('ERROR conversion:', e.message.split('\n')[0]); await shot(page, 'ERR-conversion'); }
await browser.close();
console.log('\nListo ->', OUT);
