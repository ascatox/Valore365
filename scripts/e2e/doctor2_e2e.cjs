#!/usr/bin/env node
/*
 * Portfolio Doctor 2.0 — E2E Playwright su stack reale (Postgres + FastAPI + Vite).
 *
 * Prerequisito: `scripts/e2e/doctor2_stack.sh start` (DB seminato da
 * scripts/e2e/doctor2_seed.sql, LLM finto, backend :8000 e :8001 con i flag
 * Doctor 2.0 spenti, Vite :5173). Lo script modifica il DB (policy, versioni):
 * per rieseguirlo da zero `doctor2_stack.sh stop && doctor2_stack.sh start`.
 *
 *   node scripts/e2e/doctor2_e2e.cjs                 # scenari + screenshot
 *   SCREENSHOTS=0 node scripts/e2e/doctor2_e2e.cjs   # solo scenari
 *
 * Variabili: BASE_URL (http://127.0.0.1:5173), API_URL (http://127.0.0.1:8000/api),
 * FLAGS_OFF_API (http://127.0.0.1:8001), LLM_URL (http://127.0.0.1:8765),
 * E2E_DIR / PG_PORT (psql sul cluster dello stack), SHOTS_DIR
 * (docs/doctor2/screenshots), HEADED=1.
 * `require('playwright')`: modulo globale (NODE_PATH) o installato.
 * Exit code 0 solo se tutti gli scenari passano.
 */
'use strict';

const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium, devices } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:5173';
const API_URL = process.env.API_URL || 'http://127.0.0.1:8000/api';
const FLAGS_OFF_API = process.env.FLAGS_OFF_API || 'http://127.0.0.1:8001';
const LLM_URL = process.env.LLM_URL || 'http://127.0.0.1:8765';
const E2E_DIR = process.env.E2E_DIR || '/tmp/valore365-doctor2-e2e';
const PG_PORT = process.env.PG_PORT || '55440';
const SHOTS_DIR = process.env.SHOTS_DIR || path.join(ROOT, 'docs', 'doctor2', 'screenshots');
const TAKE_SHOTS = process.env.SCREENSHOTS !== '0';

const PARENT = 1;
const WEALTH = 2;
const EXPECTED_FAIL_REASON = 'VWRA 46,6%: supera il tuo limite 35% di 11,6 punti percentuali';
const SUMMARY_RE = /^\d+ rispettat[oi] · \d+ violat[oi]( · \d+ non verificabil[ei])?( · .*)?$/;
const MONEY_RE = /\d[\d.]*(,\d+)?\s?€/;

const DESKTOP = { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 };
const TABLET = { ...devices['iPad (gen 7)'], deviceScaleFactor: 2 };
const MOBILE = { ...devices['iPhone 13'], deviceScaleFactor: 2 };

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

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
  try { json = JSON.parse(text); } catch { /* not json */ }
  return { status: response.status, json, text };
}

function psql(sql) {
  return execFileSync('psql', ['-qAt', '-h', E2E_DIR, '-p', PG_PORT, '-U', 'postgres', '-d', 'valore365', '-v', 'ON_ERROR_STOP=1', '-c', sql], { encoding: 'utf8' }).trim();
}

async function fakeLlm(pathname, body) {
  const response = await fetch(`${LLM_URL}${pathname}`, { method: body === undefined ? 'GET' : 'POST', body });
  return response.json();
}

function scopeValue(ids) {
  return ids.length > 1 ? { mode: 'aggregate', ids } : { mode: 'single', id: ids[0] };
}

async function newContext(device, ids, { privacy = false } = {}) {
  const context = await browser.newContext({ ...device, locale: 'it-IT', timezoneId: 'Europe/Rome' });
  await context.addInitScript(([scope, privacyMode]) => {
    try {
      if (!window.sessionStorage.getItem('__e2e_init')) {
        window.localStorage.setItem('valore365.portfolioScope', JSON.stringify(scope));
        window.localStorage.setItem('valore365.settings.privacyModeEnabled', privacyMode ? 'true' : 'false');
        window.sessionStorage.setItem('__e2e_init', '1');
      }
    } catch { /* storage unavailable */ }
  }, [scopeValue(ids), privacy]);
  context.consoleErrors = [];
  context.on('page', (page) => {
    page.on('pageerror', (error) => context.consoleErrors.push(String(error)));
  });
  return context;
}

async function openDoctor(context, section) {
  const page = await context.newPage();
  page.setDefaultTimeout(20000);
  await page.goto(`${BASE_URL}/doctor${section ? `?section=${section}` : ''}`);
  await page.getByRole('heading', { name: 'Doctor', exact: true }).waitFor();
  return page;
}

/** Mantine Select: open by label (inside `scope`) and click the option. */
async function chooseOption(page, scope, label, option) {
  await scope.getByRole('textbox', { name: label, exact: true }).click();
  await page.getByRole('option', { name: option, exact: true }).click();
}

async function addRule(page, modal, metricLabel) {
  await chooseOption(page, modal, 'Aggiungi una regola', metricLabel);
  await modal.getByRole('button', { name: 'Aggiungi', exact: true }).click();
}

async function shot(page, name, { fullPage = false, locator = null } = {}) {
  if (!TAKE_SHOTS) return;
  fs.mkdirSync(SHOTS_DIR, { recursive: true });
  const file = path.join(SHOTS_DIR, `${name}.jpg`);
  if (locator) await locator.screenshot({ path: file, type: 'jpeg', quality: 72 });
  else await page.screenshot({ path: file, type: 'jpeg', quality: 72, fullPage });
  log(`    screenshot ${path.relative(ROOT, file)}`);
}

async function scenario(name, fn) {
  const started = Date.now();
  try {
    await fn();
    results.push({ name, ok: true, ms: Date.now() - started });
    log(`PASS ${name} (${Date.now() - started} ms)`);
  } catch (error) {
    results.push({ name, ok: false, ms: Date.now() - started, error: String(error && error.stack || error) });
    log(`FAIL ${name}\n     ${String(error && error.message || error).split('\n').join('\n     ')}`);
  }
}

async function policyOf(ids) {
  const query = ids.map((id) => `portfolio_ids=${id}`).join('&');
  const response = await api(`/doctor/policies?${query}`);
  return response.json ? response.json.policy : null;
}

async function evaluationOf(ids) {
  const query = ids.map((id) => `portfolio_ids=${id}`).join('&');
  return (await api(`/doctor/evaluation?${query}`)).json;
}

/** Saves a policy through the public API (preview → token → save), like the UI does. */
async function savePolicyViaApi(ids, document, name) {
  const current = await policyOf(ids);
  const baseVersion = current ? current.current_version : null;
  const preview = await api('/doctor/policies/preview', { method: 'POST', body: { portfolio_ids: ids, document, base_version: baseVersion, source: 'manual' } });
  assert(preview.status === 200 && preview.json.confirmation_token, `preview failed: ${preview.text}`);
  const saved = await api('/doctor/policies', { method: 'POST', body: { portfolio_ids: ids, name, document: preview.json.normalized_document, base_version: baseVersion, confirmation_token: preview.json.confirmation_token } });
  assert(saved.status === 201, `save failed: ${saved.status} ${saved.text}`);
  return saved.json;
}

async function sendCopilot(page, text) {
  const input = page.getByPlaceholder('Chiedi al Copilot...');
  await input.fill(text);
  await page.getByRole('button', { name: 'Invia messaggio' }).click();
}

// ---------------------------------------------------------------------------
// scenarios
// ---------------------------------------------------------------------------

async function createPolicyManually() {
  assert((await policyOf([PARENT])) === null, 'Parent should start without a policy');
  const context = await newContext(DESKTOP, [PARENT]);
  const page = await openDoctor(context, 'parametri');
  const calls = [];
  page.on('request', (request) => { if (request.url().includes('/api/doctor/policies')) calls.push(`${request.method()} ${new URL(request.url()).pathname}`); });

  await page.getByRole('button', { name: 'Imposta i parametri' }).click();
  const modal = page.getByRole('dialog');
  await modal.getByText('Modifica i tuoi parametri').waitFor();

  await addRule(page, modal, 'Peso massimo singola posizione');
  const single = modal.getByTestId('rule-editor-max-single-position');
  await single.getByLabel('Valore massimo (%)').fill('35');
  await chooseOption(page, single, 'Severità', 'Alta');
  await single.getByLabel('Etichetta (opzionale)').fill('Max singolo ETF');

  await addRule(page, modal, 'Esposizione USA (look-through)');
  const usa = modal.getByTestId('rule-editor-usa-exposure');
  await usa.getByLabel('Valore massimo (%)').fill('45');
  await usa.getByLabel('Copertura minima (%)').fill('95');

  await addRule(page, modal, 'Quota azionaria');
  const equity = modal.getByTestId('rule-editor-equity-weight');
  await equity.getByRole('radio', { name: 'Intervallo' }).check({ force: true });
  await equity.getByLabel('Valore minimo (%)').fill('40');
  await equity.getByLabel('Valore massimo (%)').fill('60');

  // validate (field errors inline) first: an invalid threshold is rejected by the backend.
  await single.getByLabel('Valore massimo (%)').fill('135');
  await modal.getByRole('button', { name: 'Verifica e anteprima' }).click();
  await single.getByText(/100/).first().waitFor();
  assert(!calls.some((call) => call.endsWith('/preview')), `preview must not run on an invalid draft: ${calls}`);
  await single.getByLabel('Valore massimo (%)').fill('35');

  await modal.getByRole('button', { name: 'Verifica e anteprima' }).click();
  await modal.getByText('Conferma le modifiche').waitFor();
  assert(calls.includes('POST /api/doctor/policies/validate') && calls.includes('POST /api/doctor/policies/preview'), `validate+preview expected, got ${calls}`);
  const previewText = await modal.getByTestId('policy-preview-summary').innerText();
  assert(previewText.includes('Prima: nessun parametro impostato'), `preview before: ${previewText}`);
  assert(previewText.includes('Dopo: 1 rispettato · 1 violato · 1 non verificabile'), `preview after: ${previewText}`);
  assert((await policyOf([PARENT])) === null, 'nothing saved before «Conferma e salva»');

  await modal.getByRole('button', { name: 'Conferma e salva' }).click();
  await page.getByText('Parametri salvati: versione 1.').waitFor();
  const policy = await policyOf([PARENT]);
  assert(policy && policy.current_version === 1 && policy.document.rules.length === 3, `saved v1 expected: ${JSON.stringify(policy)}`);
  await context.close();
}

async function evaluationFailUnknown() {
  const context = await newContext(DESKTOP, [PARENT]);
  const page = await openDoctor(context, 'parametri');
  const summary = (await page.getByTestId('rules-summary').innerText()).trim();
  assert(summary === '1 rispettato · 1 violato · 1 non verificabile', `summary: ${summary}`);
  assert(!/\d+\s*\/\s*\d+/.test(summary), 'summary must not use x/y');
  const failCard = page.getByTestId('rule-card-max-single');
  await failCard.getByText(EXPECTED_FAIL_REASON, { exact: true }).waitFor();
  assert((await failCard.getByTestId('rule-status').innerText()).includes('Violato'), 'FAIL badge text');
  const usaCard = page.getByTestId('rule-card-usa-exposure');
  const usaText = await usaCard.innerText();
  assert(usaText.includes('Non verificabile') && usaText.includes('Non possiamo verificare il limite USA: copertura insufficiente'), `USA UNKNOWN: ${usaText}`);
  assert(usaText.includes('tra 40,9% e 50,3%') || usaText.includes('45,1%'), `USA bounds/value shown: ${usaText}`);
  // status is text + icon, not colour only
  for (const tone of ['fail', 'unknown', 'pass']) {
    const badge = page.locator(`[data-testid="rule-status"][data-tone="${tone}"]`).first();
    assert((await badge.innerText()).trim().length > 0, `badge ${tone} has text`);
    assert(await badge.locator('svg').count() > 0, `badge ${tone} has icon`);
  }
  await shot(page, 'desktop-parametri');

  // Diagnosi: separate summary card, same wording, never x/y
  await page.getByRole('tab', { name: 'Diagnosi' }).click();
  const card = page.getByTestId('policy-summary-card');
  const cardSummary = (await card.getByTestId('policy-summary-text').innerText()).trim();
  assert(cardSummary === summary, `Diagnosi summary: ${cardSummary}`);
  await card.getByText(EXPECTED_FAIL_REASON).waitFor();
  await shot(page, 'desktop-diagnosi');
  await context.close();
}

async function evidenceDrawer() {
  const context = await newContext(DESKTOP, [PARENT]);
  const page = await openDoctor(context, 'parametri');
  await page.getByTestId('rule-card-max-single').click();
  const evidence = page.getByTestId('policy-evidence');
  await evidence.waitFor();
  const text = await evidence.innerText();
  for (const expected of ['VWRA', 'IE00BK5BQT80', '46,6%', '685.000,00', 'doctor-policy-1.0', 'Formula e metodologia', 'Denominatore']) {
    assert(text.includes(expected), `evidence missing «${expected}»: ${text}`);
  }
  assert(!/Quote al\s+\d{2}\/\d{2}\/\d{4},?\s+\d{2}:\d{2}/.test(text), `quote date shown with a fake time: ${text}`);
  await shot(page, 'desktop-evidenza');
  await page.keyboard.press('Escape');
  await context.close();
}

async function versionsAndRestore() {
  // v2: max single 30 via the editor (from the evidence drawer «Modifica»)
  const context = await newContext(DESKTOP, [PARENT]);
  const page = await openDoctor(context, 'parametri');
  await page.getByRole('button', { name: 'Modifica parametri' }).click();
  const modal = page.getByRole('dialog');
  await modal.getByTestId('rule-editor-max-single').getByLabel('Valore massimo (%)').fill('30');
  await modal.getByRole('button', { name: 'Verifica e anteprima' }).click();
  await modal.getByTestId('policy-diff').getByText('max 35,0% → max 30,0%').waitFor();
  await modal.getByRole('button', { name: 'Conferma e salva' }).click();
  await page.getByText('Parametri salvati: versione 2.').waitFor();
  await page.getByTestId('rule-card-max-single').getByText('VWRA 46,6%: supera il tuo limite 30% di 16,6 punti percentuali').waitFor();

  await page.getByRole('button', { name: 'Versioni e audit' }).click();
  const history = page.getByTestId('policy-version-history');
  await history.getByTestId('policy-version-2').getByText('Attuale').waitFor();
  await history.getByRole('button', { name: 'Ripristina la versione 1' }).click();
  await page.getByRole('dialog').getByText('diventeranno una nuova versione (3)').waitFor();
  await page.getByRole('button', { name: 'Conferma ripristino' }).click();
  await page.getByText('Versione ripristinata: ora è la versione 3.').waitFor();
  await page.getByTestId('rule-card-max-single').getByText(EXPECTED_FAIL_REASON).waitFor();
  const versions = (await api(`/doctor/policies/${(await policyOf([PARENT])).id}/versions`)).json.versions;
  assert(versions.length === 3 && versions[0].source === 'restore' && versions[0].version_number === 3, `versions: ${JSON.stringify(versions.map((v) => [v.version_number, v.source]))}`);
  await context.close();
}

async function concurrentEditConflict() {
  const contextA = await newContext(DESKTOP, [PARENT]);
  const contextB = await newContext(DESKTOP, [PARENT]);
  const pageA = await openDoctor(contextA, 'parametri');
  const pageB = await openDoctor(contextB, 'parametri');
  for (const page of [pageA, pageB]) {
    await page.getByRole('button', { name: 'Modifica parametri' }).click();
  }
  // B prepares its preview on v3 ...
  const modalB = pageB.getByRole('dialog');
  await modalB.getByTestId('rule-editor-equity-weight').getByLabel('Valore massimo (%)').fill('70');
  await modalB.getByRole('button', { name: 'Verifica e anteprima' }).click();
  await modalB.getByText('Conferma le modifiche').waitFor();
  // ... A saves first (v4) ...
  const modalA = pageA.getByRole('dialog');
  await modalA.getByTestId('rule-editor-equity-weight').getByLabel('Valore massimo (%)').fill('65');
  await modalA.getByRole('button', { name: 'Verifica e anteprima' }).click();
  await modalA.getByRole('button', { name: 'Conferma e salva' }).click();
  await pageA.getByText('Parametri salvati: versione 4.').waitFor();
  // ... B's save gets 409 version_conflict and the reload message
  const conflictResponse = pageB.waitForResponse((r) => r.url().endsWith('/api/doctor/policies') && r.request().method() === 'POST');
  await modalB.getByRole('button', { name: 'Conferma e salva' }).click();
  const response = await conflictResponse;
  assert(response.status() === 409, `B save status ${response.status()}`);
  const body = await response.json();
  assert(body.error.code === 'version_conflict' && body.error.details.current_version === 4, `409 body ${JSON.stringify(body)}`);
  await modalB.getByTestId('policy-conflict').getByText("La policy è stata modificata in un'altra scheda: ricarica").waitFor();
  const policy = await policyOf([PARENT]);
  assert(policy.current_version === 4 && policy.document.rules.find((r) => r.rule_id === 'equity-weight').max_value === 65, 'A wins, B does not overwrite');
  await modalB.getByRole('button', { name: 'Ricarica' }).click();
  await contextA.close();
  await contextB.close();
}

async function aggregateScopePolicy() {
  const ids = [PARENT, WEALTH];
  const parentBefore = await policyOf([PARENT]);
  const context = await newContext(DESKTOP, ids);
  const page = await openDoctor(context, 'parametri');
  await page.locator('[data-state="aggregate_scope"]').first().waitFor();
  await page.locator('[data-state="no_policy"]').waitFor(); // single-portfolio policies are not merged in
  await page.getByRole('button', { name: 'Imposta i parametri' }).click();
  const modal = page.getByRole('dialog');
  await addRule(page, modal, 'Peso massimo singola posizione');
  const single = modal.getByTestId('rule-editor-max-single-position');
  await single.getByLabel('Valore massimo (%)').fill('50');
  await modal.getByRole('button', { name: 'Verifica e anteprima' }).click();
  await modal.getByRole('button', { name: 'Conferma e salva' }).click();
  await page.getByText('Parametri salvati: versione 1.').waitFor();
  const aggregate = await policyOf(ids);
  assert(aggregate && aggregate.scope.scope_type === 'aggregate' && aggregate.scope.fingerprint === 'p:1,2' && aggregate.current_version === 1, `aggregate policy ${JSON.stringify(aggregate && aggregate.scope)}`);
  const parentAfter = await policyOf([PARENT]);
  assert(parentAfter.id !== aggregate.id && parentAfter.current_version === parentBefore.current_version, 'Parent policy untouched');
  // Wealth has a stale EIMI quote: the aggregate rule is UNKNOWN (never PASS), with the stale warning
  const card = page.getByTestId('rule-card-max-single-position');
  const text = await card.innerText();
  assert(text.includes('Non verificabile') && text.includes('quotazioni non aggiornate per EIMI'), `aggregate stale UNKNOWN: ${text}`);
  await context.close();
}

async function copilotDraftCard() {
  assert((await policyOf([WEALTH])) === null, 'Wealth starts without policy');
  const context = await newContext(DESKTOP, [WEALTH]);
  const page = await openDoctor(context);
  const saves = [];
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/doctor/policies') saves.push(request.url());
  });
  await page.getByRole('button', { name: 'Apri Doctor Copilot' }).click();
  await sendCopilot(page, 'Vorrei 60/40: prepara una bozza dei miei parametri');
  const card = page.getByTestId('policy-draft-card');
  await card.waitFor({ timeout: 30000 });
  await card.getByText('Non ancora salvata').waitFor();
  const cardText = await card.innerText();
  assert(cardText.includes('Azioni 55–65%') && cardText.includes('Obbligazioni 35–45%'), `draft diff: ${cardText}`);
  assert(cardText.includes('Prima: nessun parametro impostato'), `draft before: ${cardText}`);
  await page.getByText("non è salvata finché non premi «Conferma e salva»").waitFor();
  // nothing saved yet, and the token never reached the LLM
  assert(saves.length === 0, 'no save before the click');
  assert((await policyOf([WEALTH])) === null, 'Wealth still without policy after the draft');
  const tokensInDb = Number(psql("select count(*) from doctor_confirmation_tokens where source = 'copilot' and used_at is null"));
  assert(tokensInDb >= 1, 'a copilot confirmation token was issued');
  await shot(page, 'desktop-copilot-bozza');

  await card.getByRole('button', { name: 'Conferma e salva' }).click();
  await card.getByText('Salvata').waitFor();
  assert(saves.length === 1, `one save after the click (${saves.length})`);
  const saved = await policyOf([WEALTH]);
  assert(saved && saved.current_version === 1 && saved.name === 'Policy 60/40', `saved draft ${JSON.stringify(saved)}`);
  const versions = (await api(`/doctor/policies/${saved.id}/versions`)).json.versions;
  assert(versions[0].source === 'copilot', `source copilot: ${versions[0].source}`);
  await context.close();
}

async function staleUnknownWealth() {
  const context = await newContext(DESKTOP, [WEALTH]);
  const page = await openDoctor(context, 'parametri');
  const summary = (await page.getByTestId('rules-summary').innerText()).trim();
  assert(summary === '0 rispettati · 0 violati · 3 non verificabili', `stale summary: ${summary}`);
  const reasons = await page.locator('[data-testid^="rule-card-"]').allInnerTexts();
  assert(reasons.every((r) => r.includes('quotazioni non aggiornate per EIMI') && r.includes('Non verificabile')), `stale reasons: ${reasons}`);
  await page.getByRole('tab', { name: 'Diagnosi' }).click();
  await page.getByTestId('policy-summary-card').getByText('Quotazioni non aggiornate: alcune regole non sono verificabili').waitFor();
  await context.close();
}

async function labNewCashAndCompare() {
  const context = await newContext(DESKTOP, [PARENT]);
  const page = await openDoctor(context, 'laboratorio');
  const builder = page.getByTestId('scenario-builder-0');
  await builder.waitFor();
  await builder.getByLabel('Scenario A').fill('Solo versamenti');
  const preview = page.waitForResponse((r) => r.url().includes('/api/doctor/scenarios/preview'));
  await page.getByRole('button', { name: 'Simula scenario' }).click();
  const response = await preview;
  assert(response.status() === 200, `scenario preview ${response.status()}`);
  const body = await response.json();
  assert(body.required_new_cash === 227028.58 && body.feasible === false && body.infeasible_code === 'insufficient_cash', `scenario body ${JSON.stringify({ r: body.required_new_cash, f: body.feasible, c: body.infeasible_code })}`);
  const results = page.getByTestId('lab-results');
  await results.waitFor();
  const required = (await results.getByTestId('required-new-cash').innerText()).trim();
  assert(required.replace(/\s/g, ' ') === '227.029 €', `required capital shown: «${required}»`);
  const feasibility = await results.getByTestId('scenario-feasibility').innerText();
  assert(feasibility.includes('non fattibile') && feasibility.includes('servono almeno 227.029 €'), `infeasible reason: ${feasibility}`);
  assert(!/Costi ipotetici\s*N\/D/.test(feasibility), `costs must be shown: ${feasibility}`);
  await results.getByText('Simulazione teorica; nessun ordine eseguito.').first().waitFor();

  // scenario B: the required cash → compare (table on desktop)
  await page.getByRole('button', { name: 'Aggiungi scenario' }).click();
  const builderB = page.getByTestId('scenario-builder-1');
  await builderB.getByLabel('Scenario B').fill('Versamento 227.029 €');
  await builderB.getByLabel('Nuova liquidità da investire').fill('227029');
  const compare = page.waitForResponse((r) => r.url().includes('/api/doctor/scenarios/compare'));
  await page.getByRole('button', { name: 'Confronta scenari' }).click();
  const compareResponse = await compare;
  assert(compareResponse.status() === 200, `compare ${compareResponse.status()} ${await compareResponse.text()}`);
  const table = page.getByTestId('scenario-comparison-table');
  await table.waitFor();
  const tableText = await table.innerText();
  assert(tableText.includes('Attuale') && tableText.includes('Solo versamenti') && tableText.includes('Versamento 227.029 €'), `table headers: ${tableText.slice(0, 300)}`);
  assert(tableText.includes('46,6%') && tableText.includes('35,0%'), `max single before/after: ${tableText}`);
  assert(/0 rispettati · 1 violato · 1 non verificabile|1 rispettato · 1 violato · 1 non verificabile/.test(tableText), `compliance row: ${tableText}`);
  assert(await page.getByTestId('scenario-comparison-cards').count() === 0, 'no cards on desktop');
  await shot(page, 'desktop-laboratorio-confronto', { locator: results });
  await context.close();
}

async function labCompareMobileCards() {
  const context = await newContext(MOBILE, [PARENT]);
  const page = await openDoctor(context, 'laboratorio');
  await page.getByRole('button', { name: 'Aggiungi scenario' }).click();
  await page.getByTestId('scenario-builder-1').getByLabel('Nuova liquidità da investire').fill('227029');
  await page.getByRole('button', { name: 'Confronta scenari' }).click();
  const cards = page.getByTestId('scenario-comparison-cards');
  await cards.waitFor();
  assert(await page.getByTestId('scenario-comparison-table').count() === 0, 'no wide table on mobile');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(overflow <= 1, `horizontal overflow on mobile: ${overflow}px`);
  await context.close();
}

async function privacyMode() {
  const context = await newContext(DESKTOP, [PARENT], { privacy: true });
  const page = await openDoctor(context, 'laboratorio');
  await page.getByRole('button', { name: 'Simula scenario' }).click();
  const results = page.getByTestId('lab-results');
  await results.waitFor();
  const labText = await results.innerText();
  assert((await results.getByTestId('required-new-cash').innerText()).trim() === '******', 'required cash masked');
  const amounts = labText.split('\n').filter((line) => MONEY_RE.test(line));
  assert(amounts.length === 0, `€ amounts visible in Privacy Mode: ${amounts.join(' | ')}`);
  await page.getByRole('tab', { name: 'I miei parametri' }).click();
  await page.getByTestId('rule-card-max-single').click();
  const evidence = page.getByTestId('policy-evidence');
  await evidence.waitFor();
  assert((await evidence.getByTestId('evidence-denominator-value').innerText()).trim() === '******', 'denominator masked');
  const evidenceAmounts = (await evidence.innerText()).split('\n').filter((line) => MONEY_RE.test(line));
  assert(evidenceAmounts.length === 0, `€ amounts in evidence: ${evidenceAmounts}`);
  await context.close();
}

async function llmFailureKeepsDoctor() {
  await fakeLlm('/__fail', 'on');
  try {
    const context = await newContext(DESKTOP, [PARENT]);
    const page = await openDoctor(context, 'parametri');
    await page.getByRole('button', { name: 'Apri Doctor Copilot' }).click();
    await sendCopilot(page, 'Spiegami le violazioni');
    await page.getByText(/errore|non disponibile|riprova/i).last().waitFor({ timeout: 45000 });
    // the Doctor still answers without the LLM
    await page.getByTestId('rule-card-max-single').getByText(EXPECTED_FAIL_REASON).waitFor();
    await page.getByRole('button', { name: 'Modifica parametri' }).click();
    const modal = page.getByRole('dialog');
    await modal.getByRole('button', { name: 'Verifica e anteprima' }).click();
    await modal.getByText('Conferma le modifiche').waitFor();
    await modal.getByRole('button', { name: 'Torna alle modifiche' }).click();
    await modal.getByRole('button', { name: 'Annulla' }).click();
    const evaluation = await evaluationOf([PARENT]);
    assert(evaluation.status === 'ready' && evaluation.summary.failed === 1, 'evaluation unaffected by LLM failure');
    await context.close();
  } finally {
    await fakeLlm('/__fail', 'off');
  }
}

async function providerErrorsDegrade() {
  // 1) a failed price sync → data quality "stale", every rule UNKNOWN (never PASS), warning in Diagnosi
  psql("insert into market_data_sync_runs (trigger, status, started_at, finished_at, error) values ('scheduler', 'failed', now(), now(), 'provider timeout')");
  try {
    const evaluation = await evaluationOf([PARENT]);
    assert(evaluation.data_quality.status === 'stale' && evaluation.summary.passed === 0 && evaluation.summary.unknown === 3, `sync failed evaluation ${JSON.stringify(evaluation.summary)} ${evaluation.data_quality.status}`);
    const context = await newContext(DESKTOP, [PARENT]);
    const page = await openDoctor(context);
    const card = page.getByTestId('policy-summary-card');
    await card.getByText('0 rispettati · 0 violati · 3 non verificabili').waitFor();
    await card.getByText('Quotazioni non aggiornate: alcune regole non sono verificabili').waitFor();
    await page.getByRole('tab', { name: 'I miei parametri' }).click();
    await page.getByTestId('rule-card-max-single').getByText("l'ultima sincronizzazione dei prezzi è fallita").waitFor();
    // 2) a manual price refresh with the provider unreachable: the page survives
    const refresh = await api('/prices/refresh', { method: 'POST', body: { portfolio_id: PARENT } });
    assert(refresh.status < 500 || refresh.json, `refresh answered ${refresh.status}`);
    await page.reload();
    await page.getByTestId('rule-card-max-single').waitFor();
    assert(context.consoleErrors.length === 0, `page errors: ${context.consoleErrors}`);
    await context.close();
  } finally {
    psql("delete from market_data_sync_runs where status = 'failed'");
  }
  const evaluation = await evaluationOf([PARENT]);
  assert(evaluation.summary.failed === 1, 'evaluation back to FAIL once the sync is fine');
}

async function fireDeepLink() {
  const context = await newContext(DESKTOP, [PARENT]);
  const page = await openDoctor(context, 'laboratorio');
  const fireLink = page.getByRole('link', { name: 'Vai alla pagina FIRE' });
  assert(await fireLink.getAttribute('href') === '/fire', 'Lab FIRE link');
  await page.getByRole('button', { name: 'Apri Doctor Copilot' }).click();
  await sendCopilot(page, 'Quanto capitale mi serve per andare in pensione?');
  const link = page.getByRole('link', { name: 'Apri FIRE' });
  await link.waitFor({ timeout: 30000 });
  await link.click();
  await page.waitForURL(/\/fire$/);
  await context.close();
}

async function featureFlagsOff() {
  const features = await api('/api/doctor/features', { base: FLAGS_OFF_API });
  assert(features.json.policy_enabled === false && features.json.simulator_enabled === false, 'flags-off backend');
  const disabled = await api('/api/doctor/evaluation?portfolio_ids=1', { base: FLAGS_OFF_API });
  assert(disabled.status === 404 && disabled.json.error.code === 'feature_disabled', `evaluation with flags off ${disabled.status}`);
  const context = await newContext(DESKTOP, [PARENT]);
  await context.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const response = await route.fetch({ url: `${FLAGS_OFF_API}${url.pathname}${url.search}` });
    await route.fulfill({ response });
  });
  const page = await openDoctor(context, 'laboratorio');
  await page.getByText('Punteggi per categoria').waitFor();
  assert(await page.getByRole('tab', { name: 'I miei parametri' }).count() === 0, 'no Parametri tab');
  assert(await page.getByRole('tab', { name: 'Laboratorio' }).count() === 0, 'no Laboratorio tab');
  assert(await page.getByTestId('policy-summary-card').count() === 0, 'no policy summary card');
  assert(await page.getByTestId('scenario-builder-0').count() === 0, 'deep link to the Lab falls back to Diagnosi');
  await context.close();
}

// ---------------------------------------------------------------------------
// screenshots (desktop / tablet / mobile)
// ---------------------------------------------------------------------------

async function deviceScreenshots(name, device) {
  const context = await newContext(device, [PARENT]);
  const page = await openDoctor(context);
  await page.getByTestId('policy-summary-text').waitFor();
  await shot(page, `${name}-diagnosi`);
  await page.getByRole('tab', { name: 'I miei parametri' }).click();
  await page.getByTestId('rules-summary').waitFor();
  await page.getByTestId('rule-card-max-single').scrollIntoViewIfNeeded();
  await shot(page, `${name}-parametri`);
  let overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(overflow <= 1, `${name}: horizontal overflow in Parametri ${overflow}px`);
  await page.getByTestId('rule-card-max-single').click();
  await page.getByTestId('policy-evidence').waitFor();
  await page.waitForTimeout(400);
  await shot(page, `${name}-evidenza`);
  await page.keyboard.press('Escape');
  await page.getByTestId('policy-evidence').waitFor({ state: 'detached' });

  await page.getByRole('tab', { name: 'Laboratorio' }).click();
  await page.getByRole('button', { name: 'Aggiungi scenario' }).click();
  await page.getByTestId('scenario-builder-1').getByLabel('Nuova liquidità da investire').fill('227029');
  await page.getByRole('button', { name: 'Confronta scenari' }).click();
  const comparison = page.getByTestId(name === 'mobile' ? 'scenario-comparison-cards' : 'scenario-comparison-table');
  await comparison.waitFor();
  await comparison.scrollIntoViewIfNeeded();
  await shot(page, `${name}-laboratorio-confronto`);
  overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(overflow <= 1, `${name}: horizontal overflow in Laboratorio ${overflow}px`);

  // Copilot draft card (not saved: the screenshot leaves it pending)
  await page.getByRole('tab', { name: 'Diagnosi' }).click();
  await page.getByRole('button', { name: 'Apri Doctor Copilot' }).click();
  await sendCopilot(page, 'Vorrei 60/40: prepara una bozza');
  const card = page.getByTestId('policy-draft-card');
  await card.waitFor({ timeout: 30000 });
  await card.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await shot(page, `${name}-copilot-bozza`);
  const box = await page.locator('[data-copilot-layout]').first().evaluate((el) => {
    const panel = el.closest('[role="dialog"]') || el.closest('aside') || el.parentElement.parentElement;
    const rect = panel.getBoundingClientRect();
    return { width: rect.width, height: rect.height, vw: window.innerWidth, vh: window.innerHeight };
  });
  if (name === 'desktop') assert(box.width <= box.vw * 0.4, `desktop Copilot too wide: ${JSON.stringify(box)}`);
  await context.close();
}

// ---------------------------------------------------------------------------

(async () => {
  browser = await chromium.launch({ headless: process.env.HEADED !== '1' });
  const health = await api('/health');
  assert(health.status === 200, `backend not reachable at ${API_URL}`);
  log(`Doctor 2.0 E2E — ${BASE_URL} (API ${API_URL})`);

  await scenario('01 policy manuale: editor → validate → preview → conferma → v1', createPolicyManually);
  await scenario('02 evaluation FAIL (VWRA 46,6% > 35%) + UNKNOWN copertura, riepilogo testuale', evaluationFailUnknown);
  await scenario('03 drawer evidenze', evidenceDrawer);
  await scenario('04 versioni: v2 e ripristino v1 → v3', versionsAndRestore);
  await scenario('05 due contesti: il secondo salvataggio riceve 409 conflitto', concurrentEditConflict);
  await scenario('06 scope aggregato Parent+Wealth con policy propria', aggregateScopePolicy);
  await scenario('07 Copilot: card bozza, nulla salvato prima di «Conferma e salva»', copilotDraftCard);
  await scenario('08 UNKNOWN per quotazione ferma (Wealth/EIMI)', staleUnknownWealth);
  await scenario('09 Laboratorio: no-sell 227.029 € + confronto 2 scenari (tabella desktop)', labNewCashAndCompare);
  await scenario('10 Laboratorio: confronto a card su mobile', labCompareMobileCards);
  await scenario('11 Privacy Mode maschera gli importi', privacyMode);
  await scenario('12 LLM in errore: Doctor policy/evaluation funzionano', llmFailureKeepsDoctor);
  await scenario('13 errori provider/prezzi → avviso stale/UNKNOWN', providerErrorsDegrade);
  await scenario('14 deep link /fire dal Copilot e dal Laboratorio', fireDeepLink);
  await scenario('15 feature flag spenti nascondono le sezioni', featureFlagsOff);
  if (TAKE_SHOTS) {
    await scenario('16 screenshot desktop 1440x900', () => deviceScreenshots('desktop', DESKTOP));
    await scenario('17 screenshot tablet iPad', () => deviceScreenshots('tablet', TABLET));
    await scenario('18 screenshot mobile iPhone 13', () => deviceScreenshots('mobile', MOBILE));
  }

  await browser.close();
  const failed = results.filter((r) => !r.ok);
  log(`\n${results.length - failed.length} passati, ${failed.length} falliti su ${results.length}`);
  fs.writeFileSync(path.join(E2E_DIR, 'e2e-results.json'), JSON.stringify(results, null, 2));
  process.exit(failed.length ? 1 : 0);
})().catch(async (error) => {
  console.error(error);
  if (browser) await browser.close();
  process.exit(2);
});
