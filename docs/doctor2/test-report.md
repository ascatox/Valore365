# Portfolio Doctor 2.0 — Report di test

Data: 5 novembre 2026 · branch `claude/doctor-2-policy-engine` · ultimo commit verificato `dfee10f`.
Ambiente: container Linux, Python 3.13, Node 22, PostgreSQL 16.15, Chromium (Playwright).

Questo report distingue in modo esplicito:

- **eseguito e passato**: comando lanciato in questa sessione, con il conteggio stampato dal runner;
- **progettato ma non eseguito**: verifica prevista (PRD §14 o buona pratica) che non è stata lanciata qui.

Nessun risultato è riportato come passato senza essere stato eseguito.

## 1. Riepilogo

| categoria (PRD §14) | comando | risultato |
|---|---|---|
| Unit backend (tutta la suite) | `cd src/backend && python -m pytest -q tests` | **1361 passed** (0 failed) |
| Unit backend Doctor 2.0 | vedi §2.1 | **281 passed** |
| Integrazione su Postgres reale | `cd src/backend && python -m pytest -q tests/integration` | **183 passed** (di cui 21 Doctor policy) |
| Golden PRD | vedi §2.2 | **7 passed** (+ golden in evaluator/validator, §2.2) |
| Property | `python -m pytest -q tests/unit/test_doctor_scenario_properties.py` | **6 passed** |
| Security | selezione per parola chiave, vedi §2.4 | **26 passed** |
| Lint frontend | `cd src/frontend/valore-frontend && npm run lint` | **0 errori, 0 warning** |
| Build frontend | `npm run build` (`tsc && vite build`) | **OK** |
| Unit/component frontend | `npx vitest run` | **221/221 passed (35 file)** nell'ultima esecuzione; intermittente, vedi §5 |
| E2E Playwright su stack reale | `node scripts/e2e/doctor2_e2e.cjs` | **18/18 passed** (15 scenari + 3 serie screenshot) |

## 2. Backend

### 2.1 Unit Doctor 2.0 (eseguiti, tutti passati)

Comando: `cd src/backend && python -m pytest -q tests/unit/<file>.py`

| file | test |
|---|---|
| `test_doctor_policy_evaluator.py` | 41 |
| `test_doctor_policy_metrics.py` | 33 |
| `test_doctor_policy_validator.py` | 42 |
| `test_doctor_policy_routes.py` | 22 |
| `test_doctor_policy_service.py` | 9 |
| `test_doctor_scenario.py` | 47 |
| `test_doctor_scenario_properties.py` | 6 |
| `test_doctor_scenario_routes.py` | 22 |
| `test_copilot_doctor_tools.py` | 37 |
| `test_mcp_doctor_tools.py` | 22 |
| **totale** | **281** |

Integrazione: `python -m pytest -q tests/integration/test_doctor_policy_postgres.py` → **21 passed**
(cluster Postgres 16 temporaneo della fixture `pg_engine`, schema + tutte le migrazioni).

### 2.2 Golden (esempi numerici del PRD) — eseguiti, passati

Comando (7 test nominati): `python -m pytest -q` su
`test_doctor_policy_metrics.py::test_golden_asset_classes_60_35_5_and_cash_excluded`,
`::test_single_security_46_6_vs_max_35_exact_reason`, `::test_example_b_health_100_but_policy_violated_coexist`,
`test_doctor_scenario.py::test_prd_required_new_cash_golden`, `::test_prd_required_cash_is_sufficient_and_resolves_the_violation`,
`::test_prd_example_c_no_sell_no_cash_is_infeasible`, `test_doctor_scenario_routes.py::test_preview_golden_over_rest`
→ **7 passed**.

Altri golden inclusi nelle suite di §2.1 (eseguiti come parte di quei file): USA nota/non classificata →
UNKNOWN (`test_usa_known_50_unclassified_15_coverage_85_max_60_is_unknown`), TER con copertura parziale,
minimi 55+50+10 = 115% → `infeasible` (`test_infeasible_minimums_55_50_10`).

Gli stessi valori sono verificati anche **end-to-end** sul DB reale: «VWRA 46,6%: supera il tuo limite 35% di
11,6 punti percentuali» e `required_new_cash = 227028.58` mostrato come «227.029 €» (scenari E2E 02 e 09).

### 2.3 Property — eseguiti, passati

`tests/unit/test_doctor_scenario_properties.py`: **6 passed**. Sono invarianti su portafogli/scenari
generati con seed fisso (non usano `hypothesis`, che non è una dipendenza del progetto): conservazione del
valore, nessuna posizione negativa, determinismo, invarianza per permutazione.
`python -m pytest -q tests -k propert` seleziona gli stessi 6 test.

### 2.4 Security — eseguiti, passati

Non esiste un file dedicato «security»; i test di sicurezza sono distribuiti nelle suite Doctor. Selezione usata:

```
python -m pytest -q tests/unit/test_doctor_policy_*.py tests/unit/test_doctor_scenario*.py \
  tests/unit/test_copilot_doctor_tools.py tests/unit/test_mcp_doctor_tools.py \
  tests/integration/test_doctor_policy_postgres.py \
  -k 'token or owner or other_user or not_found or forbidden or allowlist or inject or sanitiz or confirmation or security or leak or mifid or rls'
```

→ **26 passed** (276 deselezionati). Copre: token di conferma monouso/scaduto/riusato, proprietà dello scope
(404 per portafogli altrui), allowlist dei tool Copilot/MCP, token mai passato al LLM, sanificazione dei testi.
Il conteggio dipende dalla selezione per parola chiave: altri test con valenza di sicurezza (es. 409 di
concorrenza, validazione stretta degli input) sono contati in §2.1 ma non qui.

Verificato anche in E2E (scenario 07): nessun `POST /api/doctor/policies` parte prima del click su
«Conferma e salva»; il token `copilot` esiste in DB ma la policy non esiste finché non si conferma.

## 3. Frontend

| comando (in `src/frontend/valore-frontend`) | esito |
|---|---|
| `npm run lint` | 0 problemi |
| `npm run build` | OK (tsc + vite build + PWA) |
| `npx vitest run` | ultima esecuzione **221 passed / 35 file**; vedi §5 per l'intermittenza |

Test frontend Doctor 2.0 (eseguiti, passati): i 7 file `DoctorPolicy.test.tsx`, `DoctorLab.test.tsx`,
`CopilotChat.policyDraft.test.tsx`, `Doctor.copilotLayout.test.tsx`, `Doctor.policy.test.tsx`,
`Doctor.alertPrompt.test.tsx`, `ScopePages.aggregate.test.tsx` → **81 passed**, più i 2 file aggiunti in questa
sessione `lab/labFormat.test.ts` (3) e `policy/policyFormat.dates.test.ts` (3) → **6 passed**.

## 4. E2E su stack reale (eseguiti)

Stack: `scripts/e2e/doctor2_stack.sh start` (Postgres 16 + seed, backend FastAPI reale in modalità dev, Vite,
LLM finto compatibile OpenAI usato dal loop agentico reale del backend, nessuna rete esterna). Istruzioni in
`scripts/e2e/README.md`. Seed: «Parent» V = 685.000 € con VWRA 319.210 € (46,6%), «Wealth» con EIMI fermo da 30 giorni.

Comando: `node scripts/e2e/doctor2_e2e.cjs` → **18 passati, 0 falliti** (commit `dfee10f`, stack appena riavviato).

| # | scenario | esito |
|---|---|---|
| 01 | policy manuale: editor → errore di validazione inline (min > max, nessuna preview) → validate → preview («Prima: nessun parametro impostato», «Dopo: 1 rispettato · 1 violato · 1 non verificabile») → nulla salvato → «Conferma e salva» → v1 | PASS |
| 02 | evaluation: riepilogo esatto «1 rispettato · 1 violato · 1 non verificabile» (mai «x/y»), FAIL con testo esatto «VWRA 46,6%: supera il tuo limite 35% di 11,6 punti percentuali», UNKNOWN USA «copertura insufficiente», badge con icona+testo; stessa frase nella card di Diagnosi | PASS |
| 03 | drawer evidenze: contributori con ISIN, denominatore 685.000,00 €, metodologia, data quote senza ora inventata | PASS |
| 04 | v2 (35 → 30), storico versioni, ripristino v1 → v3 `source=restore` | PASS |
| 05 | due contesti browser: B prepara la preview, A salva v4, B riceve **409 `version_conflict`** (`current_version` 4) e il messaggio «La policy è stata modificata in un'altra scheda: ricarica»; A non viene sovrascritto | PASS |
| 06 | scope aggregato Parent+Wealth: nessuna policy ereditata, policy propria `p:1,2` v1, policy di Parent invariata; regola UNKNOWN per quote ferme | PASS |
| 07 | Copilot (LLM finto → tool reale `preview_policy` → SSE `policy_draft`): card «Non ancora salvata», nessun salvataggio prima del click, poi salvataggio v1 con `source=copilot` | PASS |
| 08 | Wealth con EIMI fermo: «0 rispettati · 0 violati · 3 non verificabili», motivazione «quotazioni non aggiornate per EIMI», avviso in Diagnosi | PASS |
| 09 | Laboratorio no-sell solo versamenti: non fattibile, «227.029 €» (API `227028.58`), costi mostrati; confronto 2 scenari come **tabella** su desktop | PASS |
| 10 | confronto 2 scenari su iPhone 13: **card**, nessuna tabella, nessun overflow orizzontale | PASS |
| 11 | Privacy Mode: nessun importo € visibile in Laboratorio ed evidenze (`******`) | PASS |
| 12 | LLM in errore (HTTP 500): errore nel Copilot, ma evaluation, editor e preview funzionano | PASS |
| 13 | sincronizzazione prezzi fallita: stato `stale`, 3 regole UNKNOWN (mai PASS) con «l'ultima sincronizzazione dei prezzi è fallita», avviso in Diagnosi; refresh prezzi con provider irraggiungibile senza errori di pagina | PASS |
| 14 | link FIRE: dal Laboratorio (`/fire`) e dal testo di instradamento del Copilot (click → `/fire`) | PASS |
| 15 | feature flag spenti (backend reale `:8001`): `/doctor/evaluation` 404 `feature_disabled`, schede «I miei parametri»/«Laboratorio» e card di riepilogo assenti, deep link al Laboratorio → Diagnosi | PASS |
| 16–18 | screenshot desktop/tablet/mobile con controlli: nessun overflow orizzontale, badge di stato non troncati, Copilot desktop ≤ 40% della larghezza | PASS |

### Screenshot (`docs/doctor2/screenshots/`, JPEG, deviceScaleFactor 2, totale ~2,5 MB)

| vista | desktop 1440×900 | tablet iPad (gen 7) | mobile iPhone 13 |
|---|---|---|---|
| Diagnosi | `desktop-diagnosi.jpg` | `tablet-diagnosi.jpg` | `mobile-diagnosi.jpg` |
| I miei parametri | `desktop-parametri.jpg` | `tablet-parametri.jpg` | `mobile-parametri.jpg` |
| Drawer evidenze | `desktop-evidenza.jpg` | `tablet-evidenza.jpg` | `mobile-evidenza.jpg` |
| Laboratorio, confronto | `desktop-laboratorio-confronto.jpg` | `tablet-laboratorio-confronto.jpg` | `mobile-laboratorio-confronto.jpg` |
| Copilot, card bozza | `desktop-copilot-bozza.jpg` | `tablet-copilot-bozza.jpg` | `mobile-copilot-bozza.jpg` |

## 5. Bug trovati e corretti in questa sessione

| problema | correzione | test |
|---|---|---|
| `quote_as_of` è una data senza ora (`2026-11-05`): il drawer mostrava «05/11/2026, 01:00» (e il giorno precedente a ovest di UTC) | `policyFormat.ts`: `formatDateTime`/`formatDate` mostrano le date senza ora come data di calendario | `policy/policyFormat.dates.test.ts`, E2E 03 |
| Laboratorio: `required_new_cash` 227028.58 mostrato «227.028,58 €» mentre il motivo del backend dice «227.029 €» (golden PRD) | `labFormat.ts` `formatRequiredCash` (unità intere arrotondate per eccesso, solo visualizzazione), usato in `ScenarioFeasibilitySummary.tsx` | `lab/labFormat.test.ts`, E2E 09 |
| Tablet: griglia dei totali a 5 colonne con importi attaccati («690.000,00 €917.029,00 €») | `ScenarioFeasibilitySummary.tsx`: `cols={{ base: 2, sm: 3, lg: 5 }}` | screenshot tablet |
| Tablet/desktop: badge «Dati incompleti» troncati in «DATI I…» nella colonna dello scenario non fattibile (lo stato era leggibile solo dal colore) | `ScenarioComparisonTable.tsx`: badge con `miw="max-content"` | controllo E2E 16–18 (nessuna etichetta troncata) |

Verificato contro il backend (api-contracts §8.1): le altre forme del Laboratorio (`costs` come oggetto con
`total`, `violations_*` come oggetti `RuleChange`, `current`/`ranking`/`best_index` del confronto,
`snapshot_id` dell'evaluation accettato dalla preview/compare) erano già allineate nel codice corrente
(correzioni fatte in parallelo da altri agenti durante la sessione).

## 6. Lacune note e verifiche non eseguite (progettate o consigliate, NON eseguite)

- **Autenticazione Clerk reale**: E2E solo in modalità dev (`CLERK_AUTH_ENABLED=false`, utente `dev-user`);
  isolamento fra utenti verificato solo dai test unit/integrazione backend, non in browser.
- **Provider LLM reali** (OpenAI/Anthropic/Gemini): non chiamati; il Copilot è esercitato con un LLM finto
  deterministico (le decisioni del modello sono scriptate, i tool e lo streaming sono reali).
- **Provider prezzi reali**: rete esterna bloccata; i dati di mercato vengono solo dal seed.
- **Browser**: solo Chromium (con viewport/UA di iPad e iPhone); WebKit/Safari e Firefox non eseguiti.
- **Accessibilità**: nessun audit automatico (axe) né test con screen reader; verificato solo che lo stato
  delle regole abbia icona + testo e che i badge non siano troncati.
- **Test frontend intermittente**: in 2 esecuzioni complete di `npx vitest run` su circa 8 è fallito 1 test
  (non identificato: l'output era riassunto; in 5 esecuzioni successive dedicate non si è ripresentato). Le
  esecuzioni coincidevano con carico elevato (stack E2E attivo e altri agenti che modificavano i file).
- **Risolti dopo l'E2E**: il diff della bozza ora abbina le regole per `metric_code` (una regola con
  `rule_id` diverso sulla stessa metrica è «Modificata», test backend e frontend); la freccia «→» nelle card
  mobile del confronto non va più a capo da sola (test in `DoctorLab.test.tsx`); le card mostrano
  «tra X% e Y%» quando i bounds differiscono, invece della stima puntuale (falsa precisione).
- Carico/performance end-to-end non misurati in E2E.
