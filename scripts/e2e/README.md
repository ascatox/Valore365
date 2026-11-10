# Script E2E

| script | cosa fa |
|---|---|
| `rest_be_smoke.sh` | smoke REST con `curl` su un backend già avviato (`BASE_URL`, `PORTFOLIO_ID`). |
| `doctor2_stack.sh` | stack reale usa-e-getta per Portfolio Doctor 2.0: Postgres 16 + seed, LLM finto, backend e Vite. |
| `doctor2_seed.sql` | dati E2E: utente `dev-user`, portafogli EUR «Parent» (V = 685.000 €, VWRA 319.210 € = 46,6%) e «Wealth» (EIMI con quotazione ferma da 30 giorni). Date relative a `current_date`. |
| `doctor2_fake_llm.py` | server compatibile OpenAI (solo stdlib) usato dal backend come provider Copilot: chiama il tool reale `preview_policy` per le richieste «60/40»/«bozza», rimanda a `/fire` per pensione/rendita, risponde 500 con «ERRORE LLM» o dopo `POST /__fail` `on`. |
| `doctor2_e2e.cjs` | scenari Playwright (Chromium) + screenshot in `docs/doctor2/screenshots/`. |
| `tribunal_stack.sh` | stack reale usa-e-getta per il Tribunale del portafoglio: stesso seed di `doctor2_seed.sql`, LLM finto del Tribunale `:8766`, backend `:8000` e backend con `DOCTOR_TRIBUNAL_ENABLED=false` `:8001`, Vite `:5173`. |
| `tribunal_fake_llm.py` | server compatibile OpenAI (solo stdlib) per il Tribunale: legge fase e voce dalla prima riga del prompt di sistema e risponde citando i fatti del fascicolo ricevuto; a comando (`POST /__state`) aggiunge elementi avversi (numeri, fatti inesistenti, acquisti, strumenti estranei, verdetti, id interni, omoglifi), JSON non valido, risposte lente, errori 500, obbedienza a un'istruzione nascosta nel nome di uno strumento. Usato anche da `src/backend/tests/integration/test_tribunal_adversarial.py`. |
| `tribunal_e2e.cjs` | scenari Playwright del Tribunale (desktop e iPhone 13); screenshot in `$E2E_DIR/screenshots`. |
| `tribunal_eval.py` | valutazione opzionale di prompt e modello: sedute contro un provider (o il finto LLM) sui fascicoli di esempio, report di ammessi e scartati per voce e codice; `--dry-run` non chiama nessun modello. |

## Portfolio Doctor 2.0 — come eseguire

Prerequisiti: binari Postgres 16 in `/usr/lib/postgresql/16/bin` (o `PG_BIN`), `psql`, dipendenze Python del
backend, `node_modules` del frontend, Playwright con Chromium (`require('playwright')`). Da root il cluster
gira come utente `postgres` tramite `runuser` (come la fixture `pg_engine` dei test di integrazione).

```bash
scripts/e2e/doctor2_stack.sh start     # ~10 s; log e pid in /tmp/valore365-doctor2-e2e
node scripts/e2e/doctor2_e2e.cjs       # 18 scenari (15 funzionali + 3 serie di screenshot); exit 0 se tutti passano
SCREENSHOTS=0 node scripts/e2e/doctor2_e2e.cjs   # solo scenari funzionali
scripts/e2e/doctor2_stack.sh stop      # ferma tutto e cancella il cluster
```

Se `playwright` è installato globalmente: `NODE_PATH=$(npm root -g) node scripts/e2e/doctor2_e2e.cjs`.
`HEADED=1` apre il browser visibile. Risultati anche in `/tmp/valore365-doctor2-e2e/e2e-results.json`.

Cosa avvia `doctor2_stack.sh start`:

- Postgres sul socket `$E2E_DIR` (porta 55440, nessun TCP), DB `valore365` con `database/schema.sql`, tutte le
  migrazioni e il seed;
- backend `:8000` (APP_ENV=dev, Clerk disattivato → utente `dev-user`) e un secondo backend `:8001` con
  `DOCTOR_POLICY_ENABLED=false` e `DOCTOR_SIMULATOR_ENABLED=false` (lo scenario «feature flag» instrada le
  chiamate `/api` del browser su questo);
- nessuna rete esterna: `HTTP(S)_PROXY=http://127.0.0.1:9`, scheduler prezzi/barre/PAC spenti,
  `MARKET_DATA_SYNC_ON_STARTUP=false`, justETF spento; il Copilot usa `COPILOT_PROVIDER=openai` con
  `OPENAI_BASE_URL` sul LLM finto (`:8765`), quindi il loop agentico, l'allowlist dei tool e l'evento SSE
  `policy_draft` con il token di conferma sono quelli reali del backend;
- Vite `:5173` (il proxy `/api` di `vite.config.ts` punta a `localhost:8000`, per questo la porta del backend è fissa).

Lo script E2E riparte sempre dal seed: all'avvio svuota le tabelle `doctor_policy_*` e
`doctor_confirmation_tokens` e rimuove le sincronizzazioni fallite. I prezzi e le posizioni non vengono mai
modificati. Dopo una modifica al backend riavviare lo stack (uvicorn gira senza `--reload`).

## Tribunale del portafoglio — come eseguire

Stessi prerequisiti dello stack Doctor 2.0 (i due stack usano le stesse porte 8000/8001/5173: avviarne uno alla volta).

```bash
scripts/e2e/tribunal_stack.sh start     # ~10 s; log e pid in /tmp/valore365-tribunal-e2e
node scripts/e2e/tribunal_e2e.cjs       # 6 scenari; exit 0 se tutti passano
SCREENSHOTS=0 node scripts/e2e/tribunal_e2e.cjs
scripts/e2e/tribunal_stack.sh stop
```

Il finto LLM risponde con ritardi diversi per voce (`LLM_DELAYS`, default
`indicizzatore=0.6,fattoriale=1.6,prudente=2.6`), così le voci compaiono una dopo l'altra, e aggiunge a ogni
risposta elementi avversi (`LLM_ADVERSARIAL`, default `numeri,acquisto,strumenti`) che il verificatore deve
scartare: lo script controlla che nessuno di quei testi compaia nella pagina e che ogni cifra mostrata nei testi
delle voci sia il valore di un fatto del fascicolo. Lo script svuota `tribunal_sessions` e
`tribunal_daily_usage` all'avvio. Scenari: avvio dal Doctor e comparsa progressiva delle tre voci; apertura di un
fatto citato, sintesi e conteggio degli scarti; riapertura della seduta salvata senza chiamate al modello (e
riproduzione via API senza consumare il limite); vista aggregata Parent + Wealth; mobile (tab del Doctor in griglia,
voci a schede, bottom sheet del fatto, «Rifai la seduta», nessuno scroll orizzontale); flag spento.

Valutazione di prompt e modello (`tribunal_eval.py`):

```bash
python scripts/e2e/tribunal_eval.py --dry-run                       # piano e dimensione dei prompt, nessuna chiamata
python scripts/e2e/tribunal_eval.py --provider openai --model fake \
  --base-url http://127.0.0.1:8766/v1 --api-key-env NONE            # contro il finto LLM dello stack
python scripts/e2e/tribunal_eval.py --api http://127.0.0.1:8000/api --scope 1 --scope 1,2   # contro un backend avviato
OPENAI_API_KEY=... python scripts/e2e/tribunal_eval.py --provider openai --model gpt-4o-mini --repeat 3 \
  --case-file latest.json --json risultati.json                     # provider reale: 7 chiamate a pagamento per seduta
```

`--case-file` accetta un `CaseFile` o la risposta di `GET /api/doctor/tribunal/sessions/latest`; il fascicolo della
seduta d'esempio (`docs/tribunale/fixtures/seduta-esempio.json`) è sempre incluso. Il report riporta per ogni seduta
ammessi, scartati per codice ed errori per `fase:voce`, poi i totali per voce e per codice.
