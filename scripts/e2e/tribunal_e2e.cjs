#!/usr/bin/env node
/*
 * Tribunale del portafoglio — E2E Playwright su stack reale (TASK-71).
 *
 * Prerequisito: `scripts/e2e/tribunal_stack.sh start` (Postgres seminato con
 * scripts/e2e/doctor2_seed.sql, LLM finto del Tribunale con ritardi per voce ed elementi
 * avversi, backend :8000, backend con DOCTOR_TRIBUNAL_ENABLED=false :8001, Vite :5173).
 * All'avvio lo script svuota le tabelle tribunal_* (riparte sempre da zero).
 *
 *   node scripts/e2e/tribunal_e2e.cjs                 # scenari + screenshot
 *   SCREENSHOTS=0 node scripts/e2e/tribunal_e2e.cjs   # solo scenari
 *
 * Variabili: BASE_URL (http://127.0.0.1:5173), API_URL (http://127.0.0.1:8000/api),
 * FLAGS_OFF_API (http://127.0.0.1:8001), LLM_URL (http://127.0.0.1:8766),
 * E2E_DIR / PG_PORT (psql sul cluster dello stack), SHOTS_DIR ($E2E_DIR/screenshots), HEADED=1.
 * Exit code 0 solo se tutti gli scenari passano. Risultati anche in $E2E_DIR/e2e-results.json.
 */
'use strict';

const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium, devices } = require('playwright');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:5173';
const API_URL = process.env.API_URL || 'http://127.0.0.1:8000/api';
const FLAGS_OFF_API = process.env.FLAGS_OFF_API || 'http://127.0.0.1:8001';
const LLM_URL = process.env.LLM_URL || 'http://127.0.0.1:8766';
const E2E_DIR = process.env.E2E_DIR || '/tmp/valore365-tribunal-e2e';
const PG_PORT = process.env.PG_PORT || '55441';
const SHOTS_DIR = process.env.SHOTS_DIR || path.join(E2E_DIR, 'screenshots');
const TAKE_SHOTS = process.env.SCREENSHOTS !== '0';

const PARENT = 1;
const WEALTH = 2;
const VOICES = ['indicizzatore', 'fattoriale', 'prudente'];
// Testi avversi del finto LLM: non devono mai comparire nella pagina.
const FORBIDDEN = ['zqxcanary', 'zqxinjection', 'XDWD', 'LU0274208692', 'amundi', 'CSPX'];

const DESKTOP = { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 };
const MOBILE = { ...devices['iPhone 13'], deviceScaleFactor: 2 };

const results = [];
let browser;

function log(...args) { console.log(...args); }

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function api(pathname, { method = 'GET', body, base = API_URL } = {}) {
  const response = await fetch(`${base}${pathname}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let json = null;
  try { json = JSON.parse(text); } catch { /* non JSON */ }
  return { status: response.status, json, text };
}

async function fakeLlm(pathname, body) {
  const response = await fetch(`${LLM_URL}${pathname}`, {
    method: body === undefined ? 'GET' : 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return response.json();
}

function psql(sql) {
  return execFileSync('psql', ['-qAt', '-h', E2E_DIR, '-p', PG_PORT, '-U', 'postgres', '-d', 'valore365',
    '-v', 'ON_ERROR_STOP=1', '-c', sql], { encoding: 'utf8' }).trim();
}

function scopeValue(ids) {
  return ids.length > 1 ? { mode: 'aggregate', ids } : { mode: 'single', id: ids[0] };
}

async function newContext(device, ids) {
  const context = await browser.newContext({ ...device, locale: 'it-IT', timezoneId: 'Europe/Rome' });
  await context.addInitScript(([scope]) => {
    try {
      if (!window.sessionStorage.getItem('__e2e_init')) {
        window.localStorage.setItem('valore365.portfolioScope', JSON.stringify(scope));
        window.localStorage.setItem('valore365.settings.privacyModeEnabled', 'false');
        window.sessionStorage.setItem('__e2e_init', '1');
      }
    } catch { /* storage non disponibile */ }
  }, [scopeValue(ids)]);
  context.pageErrors = [];
  context.on('page', (page) => page.on('pageerror', (error) => context.pageErrors.push(String(error))));
  return context;
}

async function openTribunal(context) {
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  await page.goto(`${BASE_URL}/doctor?section=tribunale`);
  await page.getByRole('heading', { name: 'Doctor', exact: true }).waitFor();
  await page.locator('[data-testid="tribunal-section"]:not([aria-busy="true"])').first().waitFor();
  return page;
}

async function sectionState(page) {
  return page.locator('[data-testid="tribunal-section"]').first().getAttribute('data-state');
}

async function waitState(page, state, timeout = 30000) {
  await page.locator(`[data-testid="tribunal-section"][data-state="${state}"]`).first().waitFor({ timeout });
}

async function voiceArgumentCounts(page) {
  return page.evaluate((voices) => Object.fromEntries(voices.map((v) => [
    v, document.querySelectorAll(`[data-testid="tribunal-voice-${v}"] [data-testid="tribunal-argument"]`).length,
  ])), VOICES);
}

/** Nessun testo avverso; ogni cifra mostrata nei testi delle voci sta dentro un chip di un fatto. */
async function assertCleanPage(page, caseFile) {
  const body = await page.locator('body').innerText();
  for (const word of FORBIDDEN) assert(!body.includes(word), `testo avverso nella pagina: ${word}`);
  const formatted = new Set(caseFile.facts.map((f) => f.formatted));
  const report = await page.evaluate(() => {
    const out = { chips: [], residualDigits: [] };
    document.querySelectorAll('[data-testid="tribunal-rich-text"]').forEach((node) => {
      const clone = node.cloneNode(true);
      clone.querySelectorAll('[data-testid="tribunal-fact-chip"]').forEach((chip) => {
        out.chips.push(chip.textContent.trim());
        chip.remove();
      });
      const rest = clone.textContent;
      if (/[0-9%€]/.test(rest)) out.residualDigits.push(rest);
    });
    return out;
  });
  assert(report.chips.length > 0, 'nessun fatto citato nella pagina');
  for (const chip of report.chips) assert(formatted.has(chip), `valore non presente nel fascicolo: ${chip}`);
  assert(report.residualDigits.length === 0, `cifre fuori dai fatti citati: ${report.residualDigits.join(' | ')}`);
  return report.chips.length;
}

async function noHorizontalScroll(page) {
  const { scroll, width } = await page.evaluate(() => ({
    scroll: document.scrollingElement.scrollWidth, width: window.innerWidth,
  }));
  assert(scroll <= width + 1, `scroll orizzontale: ${scroll} > ${width}`);
}

async function shot(page, name, { fullPage = false } = {}) {
  if (!TAKE_SHOTS) return;
  fs.mkdirSync(SHOTS_DIR, { recursive: true });
  const file = path.join(SHOTS_DIR, `${name}.jpg`);
  await page.screenshot({ path: file, type: 'jpeg', quality: 70, fullPage });
  log(`    screenshot ${file}`);
}

async function scenario(name, fn) {
  const started = Date.now();
  try {
    await fn();
    results.push({ name, ok: true, ms: Date.now() - started });
    log(`PASS ${name} (${Date.now() - started} ms)`);
  } catch (error) {
    results.push({ name, ok: false, ms: Date.now() - started, error: String((error && error.stack) || error) });
    log(`FAIL ${name}\n     ${String((error && error.message) || error).split('\n').join('\n     ')}`);
  }
}

// ---------------------------------------------------------------------------
// scenari
// ---------------------------------------------------------------------------

const shared = { calls: 0, caseFile: null };

async function startFromDoctor() {
  const context = await newContext(DESKTOP, [PARENT]);
  try {
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    await page.goto(`${BASE_URL}/doctor`);
    await page.getByRole('heading', { name: 'Doctor', exact: true }).waitFor();
    const tabs = page.getByTestId('doctor-section-tabs');
    await tabs.getByRole('tab', { name: 'Tribunale' }).click();
    await page.waitForURL(/section=tribunale/);
    await page.locator('[data-testid="tribunal-section"]:not([aria-busy="true"])').first().waitFor();
    await page.getByTestId('tribunal-disclaimer').waitFor();
    const before = (await fakeLlm('/__calls')).length;
    await page.getByTestId('tribunal-start').click();
    // Comparsa progressiva: si campiona il DOM finché la seduta non è conclusa.
    const timeline = [];
    const deadline = Date.now() + 40000;
    while (Date.now() < deadline) {
      const state = await sectionState(page);
      timeline.push({ t: Date.now(), state, counts: await voiceArgumentCounts(page) });
      if (state === 'completed' || state === 'error') break;
      await page.waitForTimeout(150);
    }
    const last = timeline[timeline.length - 1];
    assert(last.state === 'completed', `seduta non conclusa: ${JSON.stringify(last)}`);
    const running = timeline.filter((s) => s.state === 'running');
    assert(running.length > 0, 'stato running mai osservato');
    const partialOne = running.find((s) => s.counts.indicizzatore > 0 && s.counts.prudente === 0);
    const partialTwo = running.find((s) => s.counts.fattoriale > 0 && s.counts.prudente === 0);
    assert(partialOne, `l'indicizzatore non è comparso prima del prudente: ${JSON.stringify(running.map((s) => s.counts))}`);
    assert(partialTwo, 'il fattoriale non è comparso prima del prudente');
    const firstInd = timeline.find((s) => s.counts.indicizzatore > 0).t;
    const firstPru = timeline.find((s) => s.counts.prudente > 0).t;
    assert(firstPru - firstInd >= 1000, `voci non progressive: ${firstPru - firstInd} ms`);
    for (const voice of VOICES) {
      assert(last.counts[voice] === 3, `${voice}: ${last.counts[voice]} argomenti`);
    }
    const calls = (await fakeLlm('/__calls')).length - before;
    assert(calls === 7, `chiamate al modello: ${calls} (attese 7)`);
    shared.calls = calls;
    const latest = await api(`/doctor/tribunal/sessions/latest?portfolio_ids=${PARENT}`);
    assert(latest.json && latest.json.session, 'seduta non salvata');
    shared.caseFile = latest.json.session.case_file;
    await page.getByTestId('tribunal-phases').waitFor();
    await shot(page, 'tribunale-desktop-seduta', { fullPage: true });
    assert(context.pageErrors.length === 0, `errori JS: ${context.pageErrors.join('; ')}`);
  } finally {
    await context.close();
  }
}

async function citedFactAndSynthesis() {
  const context = await newContext(DESKTOP, [PARENT]);
  try {
    const page = await openTribunal(context);
    await waitState(page, 'completed');
    const caseFile = shared.caseFile || (await api(`/doctor/tribunal/sessions/latest?portfolio_ids=${PARENT}`)).json.session.case_file;
    const chips = await assertCleanPage(page, caseFile);
    // Apertura di un fatto citato da una voce.
    const chip = page.locator('[data-testid="tribunal-voice-indicizzatore"] [data-testid="tribunal-fact-chip"]').first();
    const factId = await chip.getAttribute('data-fact-id');
    const chipText = (await chip.innerText()).trim();
    await chip.click();
    const details = page.getByTestId('tribunal-fact-details').first();
    await details.waitFor();
    const fact = caseFile.facts.find((f) => f.id === factId);
    assert(fact, `fatto ${factId} non nel fascicolo`);
    const value = (await details.getByTestId('tribunal-fact-value').innerText()).trim();
    assert(value === fact.formatted && chipText === fact.formatted, `valore ${value} / ${chipText} != ${fact.formatted}`);
    const detailsText = await details.innerText();
    assert(detailsText.includes(fact.label), `label del fatto assente: ${fact.label}`);
    await shot(page, 'tribunale-desktop-fatto');
    await page.keyboard.press('Escape');
    // Sintesi: punti condivisi, contesi, domande aperte; nessun vincitore.
    const synthesis = page.locator('[data-testid="tribunal-synthesis"]').first();
    await synthesis.waitFor();
    const synthText = await synthesis.innerText();
    assert(/concordano/.test(synthText), 'punto condiviso assente');
    assert(await page.getByTestId('tribunal-contested-point').count() === 1, 'punto conteso assente');
    assert(await page.locator('[data-testid="tribunal-open-questions"] li').count() >= 2
      || /oscillazione temporanea/.test(synthText), 'domande aperte assenti');
    assert(!/vince|vincitore|verdetto/i.test(synthText), 'la sintesi proclama un vincitore');
    // Scarti: solo conteggi.
    const discarded = page.getByTestId('tribunal-discarded');
    await discarded.waitFor();
    const title = await page.getByTestId('tribunal-discarded-title').innerText();
    assert(/\d+/.test(title), `titolo scarti senza conteggio: ${title}`);
    assert(await page.getByTestId('tribunal-rebuttal').count() === 6, 'repliche attese: 6');
    log(`    fatti citati controllati: ${chips}; scarti: ${title}`);
    await shot(page, 'tribunale-desktop-sintesi', { fullPage: true });
  } finally {
    await context.close();
  }
}

async function reopenSavedSession() {
  const before = (await fakeLlm('/__calls')).length;
  const context = await newContext(DESKTOP, [PARENT]);
  try {
    const page = await openTribunal(context);
    await page.locator('[data-testid="tribunal-section"][data-state="completed"][data-source="saved"]').waitFor();
    const counts = await voiceArgumentCounts(page);
    for (const voice of VOICES) assert(counts[voice] === 3, `seduta salvata, ${voice}: ${counts[voice]}`);
    const scope = await page.getByTestId('tribunal-scope').innerText();
    assert(/Seduta del/.test(scope), `data della seduta assente: ${scope}`);
    await page.getByTestId('tribunal-redo').waitFor();
    await assertCleanPage(page, shared.caseFile);
    await page.reload();
    await page.locator('[data-testid="tribunal-section"][data-state="completed"][data-source="saved"]').waitFor();
    const after = (await fakeLlm('/__calls')).length;
    assert(after === before, `la riapertura ha chiamato il modello (${after - before} chiamate)`);
    const status = await api(`/doctor/tribunal/status?portfolio_ids=${PARENT}`);
    assert(status.json.limit.used_today === 1, `sedute usate: ${status.json.limit.used_today}`);
    // Riavvio con fascicolo invariato: riproduzione senza modello e senza consumare il limite.
    const replay = await api('/doctor/tribunal/sessions', { method: 'POST', body: { portfolio_ids: [PARENT] } });
    assert(replay.status === 200 && replay.text.includes('"reused": true'), 'riproduzione attesa');
    assert((await fakeLlm('/__calls')).length === before, 'la riproduzione ha chiamato il modello');
    const status2 = await api(`/doctor/tribunal/status?portfolio_ids=${PARENT}`);
    assert(status2.json.limit.used_today === 1, 'la riproduzione ha consumato il limite');
  } finally {
    await context.close();
  }
}

async function aggregateView() {
  const context = await newContext(DESKTOP, [PARENT, WEALTH]);
  try {
    const page = await openTribunal(context);
    const scope = await page.getByTestId('tribunal-scope').innerText();
    assert(/Vista aggregata di 2 portafogli/.test(scope), `scope: ${scope}`);
    await page.getByTestId('tribunal-start').click();
    await waitState(page, 'completed', 40000);
    const latest = await api(`/doctor/tribunal/sessions/latest?portfolio_ids=${PARENT}&portfolio_ids=${WEALTH}`);
    const session = latest.json.session;
    assert(session && session.scope.fingerprint === 'p:1,2' && session.scope.scope_type === 'aggregate',
      `seduta aggregata: ${JSON.stringify(session && session.scope)}`);
    assert(session.case_file.notes.some((n) => /Vista aggregata/.test(n)), 'nota aggregata assente nel fascicolo');
    await assertCleanPage(page, session.case_file);
    // La seduta del solo Parent resta separata.
    const parent = await api(`/doctor/tribunal/sessions/latest?portfolio_ids=${PARENT}`);
    assert(parent.json.session.scope.fingerprint === 'p:1', 'seduta del Parent sovrascritta');
    await page.getByTestId('tribunal-actions-aggregate-note').count(); // presente solo con le azioni dei punti contesi
    await shot(page, 'tribunale-desktop-aggregata', { fullPage: true });
  } finally {
    await context.close();
  }
}

async function mobile() {
  const context = await newContext(MOBILE, [PARENT]);
  try {
    const page = await openTribunal(context);
    const tabs = page.getByTestId('doctor-section-tabs');
    assert(await tabs.getAttribute('data-layout') === 'grid', 'tab del Doctor non in griglia su mobile');
    await page.locator('[data-testid="tribunal-section"][data-state="completed"]').waitFor();
    const voices = page.locator('[data-testid="tribunal-voices"]').first();
    assert(await voices.getAttribute('data-layout') === 'tabs', 'voci non a schede su mobile');
    await noHorizontalScroll(page);
    await shot(page, 'tribunale-mobile-salvata');
    // Rifai la seduta: comparsa progressiva anche su mobile.
    await page.getByTestId('tribunal-redo').click();
    await waitState(page, 'running');
    await waitState(page, 'completed', 40000);
    await voices.getByRole('tab', { name: /prudente/i }).click();
    const prudente = page.locator('[data-testid="tribunal-voice-prudente"]');
    await prudente.waitFor();
    assert(await prudente.getByTestId('tribunal-argument').count() === 3, 'argomenti del prudente su mobile');
    const chip = prudente.getByTestId('tribunal-fact-chip').first();
    const factId = await chip.getAttribute('data-fact-id');
    await chip.click();
    const details = page.getByTestId('tribunal-fact-details').first();
    await details.waitFor();
    const caseFile = (await api(`/doctor/tribunal/sessions/latest?portfolio_ids=${PARENT}`)).json.session.case_file;
    const fact = caseFile.facts.find((f) => f.id === factId);
    assert((await details.getByTestId('tribunal-fact-value').innerText()).trim() === fact.formatted, 'valore nel bottom sheet');
    await shot(page, 'tribunale-mobile-fatto');
    await page.keyboard.press('Escape');
    await page.getByTestId('tribunal-fact-details').first().waitFor({ state: 'hidden', timeout: 5000 });
    await page.locator('[data-testid="tribunal-synthesis"]').first().scrollIntoViewIfNeeded();
    await noHorizontalScroll(page);
    await assertCleanPage(page, caseFile);
    await shot(page, 'tribunale-mobile-sintesi');
    assert(context.pageErrors.length === 0, `errori JS: ${context.pageErrors.join('; ')}`);
  } finally {
    await context.close();
  }
}

async function featureFlagOff() {
  const context = await newContext(DESKTOP, [PARENT]);
  try {
    const flags = await api('/api/doctor/features', { base: FLAGS_OFF_API });
    assert(flags.json && flags.json.tribunal_enabled === false, `features flag OFF: ${flags.text}`);
    await context.route((url) => url.pathname.startsWith('/api/'), async (route) => {
      const url = new URL(route.request().url());
      const response = await route.fetch({ url: `${FLAGS_OFF_API}${url.pathname}${url.search}` });
      await route.fulfill({ response });
    });
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    await page.goto(`${BASE_URL}/doctor?section=tribunale`);
    await page.getByRole('heading', { name: 'Doctor', exact: true }).waitFor();
    await page.getByTestId('doctor-section-tabs').waitFor();
    await page.waitForTimeout(800);
    assert(await page.getByTestId('doctor-section-tabs').getByRole('tab', { name: 'Tribunale' }).count() === 0,
      'tab Tribunale visibile con il flag spento');
    assert(await page.locator('[data-testid="tribunal-section"]:visible').count() === 0, 'sezione visibile con il flag spento');
    const off = await api('/api/doctor/tribunal/status?portfolio_ids=1', { base: FLAGS_OFF_API });
    assert(off.status === 404 && off.json.error.code === 'feature_disabled', `status flag OFF: ${off.status}`);
  } finally {
    await context.close();
  }
}

async function main() {
  psql('delete from tribunal_sessions; delete from tribunal_daily_usage;');
  const state = await fakeLlm('/__state');
  log(`LLM finto: ritardi ${JSON.stringify(state.delays)}; avversi ${JSON.stringify(state.adversarial)}`);
  browser = await chromium.launch({ headless: process.env.HEADED !== '1' });
  try {
    await scenario('01 avvio dal Doctor e comparsa progressiva delle tre voci (desktop)', startFromDoctor);
    await scenario('02 apertura di un fatto citato, sintesi, scarti solo come conteggi', citedFactAndSynthesis);
    await scenario('03 riapertura con seduta salvata (nessuna chiamata al modello)', reopenSavedSession);
    await scenario('04 vista aggregata Parent + Wealth', aggregateView);
    await scenario('05 mobile iPhone 13: griglia, schede, bottom sheet, rifai la seduta', mobile);
    await scenario('06 DOCTOR_TRIBUNAL_ENABLED=false nasconde la sezione', featureFlagOff);
  } finally {
    await browser.close();
  }
  fs.mkdirSync(E2E_DIR, { recursive: true });
  fs.writeFileSync(path.join(E2E_DIR, 'e2e-results.json'), JSON.stringify(results, null, 2));
  const failed = results.filter((r) => !r.ok);
  log(`\n${results.length - failed.length}/${results.length} scenari passati`);
  process.exit(failed.length ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(2);
});
