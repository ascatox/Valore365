# Backend Test Plan (Deferred)

## Context
Questo piano serve per completare la validazione del backend in un ambiente con accesso completo.

## Blocker attuale
- Su questo PC non e' possibile eseguire validazione completa (tooling/runtime/dependency non pienamente disponibili).

## Obiettivo
Confermare correttezza funzionale, robustezza ingest, performance minima e stabilita operativa del BE.

## Prerequisiti ambiente
- Python + pip pienamente disponibili
- PostgreSQL accessibile
- Dipendenze installabili (`requirements.txt`, `requirements-dev.txt`)
- Chiave provider finance valida (`FINANCE_API_KEY`)
- Accesso rete verso provider

## Setup
1. Copiare `src/backend/.env.example` in `src/backend/.env` e compilare i valori reali.
2. Eseguire bootstrap DB:
- `./scripts/bootstrap_db.ps1`
3. Avviare backend:
- `./scripts/run_backend.ps1`

## Test Suite (non-E2E)
1. Installare dipendenze test:
- `pip install -r src/backend/requirements-dev.txt`
2. Eseguire test:
- `python -m pytest -q src/backend/tests`
3. Criterio pass:
- Tutti i test verdi.

## Smoke API locale
1. Health:
- `GET /health` -> `200`
2. Anagrafiche:
- `POST /assets` -> `201/200`
- `POST /asset-provider-symbols` -> `201/200`
- `GET /assets/{id}` -> `200`
3. Transazioni:
- `POST /transactions` -> `200`
4. Ingest realtime:
- `POST /prices/refresh` -> `200`
5. Backfill storico:
- `POST /prices/backfill-daily?portfolio_id=1&days=365` -> `200`
6. Analytics:
- `GET /portfolios/1/summary` -> `200`
- `GET /portfolios/1/timeseries?range=1y&interval=1d` -> `200`

## Verifiche DB
- `price_ticks` popolata dopo refresh realtime
- `price_bars_1d` popolata dopo backfill daily
- `fx_rates_1d` popolata per coppie necessarie
- `api_idempotency_keys` valorizzata con header `Idempotency-Key`

## Verifica idempotenza
1. Chiamare due volte `POST /prices/refresh` con stesso `Idempotency-Key`.
2. Atteso: seconda risposta da cache idempotente.
3. Ripetere su `POST /prices/backfill-daily`.

## Verifica scheduler
1. Impostare `PRICE_SCHEDULER_ENABLED=true`.
2. Avviare backend e attendere almeno un ciclo.
3. Atteso: log start/end refresh + nuovi record `price_ticks`.

## Verifica error model
- Forzare input invalido e risorsa mancante.
- Atteso: payload uniforme
`{"error":{"code":"...","message":"..."}}`.

## Performance minima
- Backfill 365 giorni su portfolio campione completato senza errori.
- Endpoint summary/timeseries rispondono entro tempi accettabili per uso personale.

## Exit Criteria
- Test suite verde
- Smoke API completo senza errori bloccanti
- Dati realtime/storico presenti e coerenti
- Idempotenza e scheduler verificati
- Nessun blocker critico aperto

## TODO Operativo (GitHub)
- Push della commit locale `bc650a7` su `origin/main` appena disponibile accesso GitHub completo.
- Passi previsti:
  1. `git push -u origin main`
  2. verifica remoto allineato (`git status`, `git log --oneline -1`)
