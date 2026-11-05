# Script E2E

| script | cosa fa |
|---|---|
| `rest_be_smoke.sh` | smoke REST con `curl` su un backend già avviato (`BASE_URL`, `PORTFOLIO_ID`). |
| `doctor2_stack.sh` | stack reale usa-e-getta per Portfolio Doctor 2.0: Postgres 16 + seed, LLM finto, backend e Vite. |
| `doctor2_seed.sql` | dati E2E: utente `dev-user`, portafogli EUR «Parent» (V = 685.000 €, VWRA 319.210 € = 46,6%) e «Wealth» (EIMI con quotazione ferma da 30 giorni). Date relative a `current_date`. |
| `doctor2_fake_llm.py` | server compatibile OpenAI (solo stdlib) usato dal backend come provider Copilot: chiama il tool reale `preview_policy` per le richieste «60/40»/«bozza», rimanda a `/fire` per pensione/rendita, risponde 500 con «ERRORE LLM» o dopo `POST /__fail` `on`. |
| `doctor2_e2e.cjs` | scenari Playwright (Chromium) + screenshot in `docs/doctor2/screenshots/`. |

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
