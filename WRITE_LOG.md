## 2026-02-17 09:57:05
- Operazione: create
- File: database/schema.sql
- Motivo: inizializzazione schema base database portfolio tracker
- Dettagli: creato file schema con tabelle portfolios, assets, asset_provider_symbols, transactions, price_ticks, price_bars_1m, price_bars_1d, fx_rates_1d e indici correlati.

## 2026-02-17 10:01:53
- Operazione: update
- File: database/schema.sql
- Motivo: impostare nome portfolio di default a Valore365
- Dettagli: aggiunto default Valore365 Portfolio al campo portfolios.name.

## 2026-02-17 10:01:53
- Operazione: create
- File: database/seed.sql
- Motivo: seed portfolio di default
- Dettagli: aggiunto inserimento portfolio iniziale Valore365 Portfolio in EUR/Europe-Rome.

## 2026-02-17 10:01:53
- Operazione: create
- File: src/, src/backend/, src/frontend/, docs/, scripts/
- Motivo: struttura base progetto
- Dettagli: create cartelle base per sviluppo backend, frontend, documentazione e script.

## 2026-02-17 10:01:53
- Operazione: create
- File: README.md
- Motivo: inizializzazione documentazione progetto
- Dettagli: aggiunti obiettivi V1, struttura directory e passi iniziali di avvio.

## 2026-02-17 10:05:54
- Operazione: update
- File: Valore365/
- Motivo: riorganizzazione root progetto
- Dettagli: creata cartella root Valore365 e spostati al suo interno tutti i file e le cartelle esistenti del workspace.

## 2026-02-17 10:37:52
- Operazione: create
- File: src/backend/app/main.py
- Motivo: bootstrap API FastAPI V1
- Dettagli: aggiunti endpoint health, transactions, positions, summary, timeseries, allocation, assets search.

## 2026-02-17 10:37:52
- Operazione: create
- File: src/backend/app/models.py
- Motivo: definizione contratti API
- Dettagli: aggiunti modelli Pydantic per request/response delle API minime.

## 2026-02-17 10:37:52
- Operazione: create
- File: src/backend/app/store.py
- Motivo: implementazione logica minima V1
- Dettagli: aggiunto store in-memory con gestione transazioni, posizioni, summary, timeseries e allocation.

## 2026-02-17 10:37:52
- Operazione: create
- File: src/backend/app/__init__.py
- Motivo: esportazione app package backend
- Dettagli: aggiunto export esplicito di app FastAPI.

## 2026-02-17 10:37:52
- Operazione: create
- File: src/backend/requirements.txt
- Motivo: dipendenze backend minime
- Dettagli: aggiunte dipendenze FastAPI, Uvicorn, Pydantic.

## 2026-02-17 10:37:52
- Operazione: create
- File: src/backend/README.md
- Motivo: documentazione avvio backend
- Dettagli: aggiunti endpoint disponibili e comandi run locale.

## 2026-02-17 10:37:52
- Operazione: update
- File: README.md
- Motivo: allineamento documentazione root al backend minimo
- Dettagli: aggiunta sezione backend API minimo e aggiornato avvio placeholder.

## 2026-02-17 10:37:52
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate tutte le scritture effettuate per bootstrap backend V1.

## 2026-02-17 10:41:34
- Operazione: update
- File: src/backend/app/models.py
- Motivo: compatibilita input transazione con DB
- Dettagli: 	rade_at aggiornato da stringa a datetime.

## 2026-02-17 10:41:34
- Operazione: create
- File: src/backend/app/db.py
- Motivo: configurazione connessione PostgreSQL
- Dettagli: aggiunto engine SQLAlchemy con DATABASE_URL da variabile ambiente.

## 2026-02-17 10:41:34
- Operazione: create
- File: src/backend/app/repository.py
- Motivo: integrazione persistenza dati
- Dettagli: implementato repository SQL per transazioni, posizioni, summary, allocation, timeseries e ricerca asset.

## 2026-02-17 10:41:34
- Operazione: update
- File: src/backend/app/main.py
- Motivo: wiring API verso DB
- Dettagli: sostituito store in-memory con repository PostgreSQL e gestione errori HTTP.

## 2026-02-17 10:41:34
- Operazione: update
- File: src/backend/requirements.txt
- Motivo: dipendenze DB backend
- Dettagli: aggiunte dipendenze sqlalchemy e psycopg[binary].

## 2026-02-17 10:41:34
- Operazione: update
- File: src/backend/README.md
- Motivo: documentazione setup DB
- Dettagli: aggiunti prerequisiti PostgreSQL, DATABASE_URL e run aggiornato.

## 2026-02-17 10:41:34
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate tutte le modifiche per collegamento backend a PostgreSQL.

## 2026-02-17 10:43:29
- Operazione: create
- File: src/backend/app/config.py
- Motivo: configurazione centralizzata backend
- Dettagli: aggiunte impostazioni per ambiente, database e chiavi API provider finanziario con caricamento da .env.

## 2026-02-17 10:43:29
- Operazione: update
- File: src/backend/app/db.py
- Motivo: usare configurazione centralizzata
- Dettagli: connessione SQLAlchemy aggiornata per leggere database_url da config.py.

## 2026-02-17 10:43:29
- Operazione: update
- File: src/backend/requirements.txt
- Motivo: supporto settings da file
- Dettagli: aggiunta dipendenza pydantic-settings.

## 2026-02-17 10:43:29
- Operazione: create
- File: src/backend/.env.example
- Motivo: template configurazione locale
- Dettagli: aggiunte variabili APP_ENV, DATABASE_URL e chiavi provider finance.

## 2026-02-17 10:43:29
- Operazione: create
- File: src/backend/.gitignore
- Motivo: protezione segreti locali
- Dettagli: esclusi .env, .venv e file cache python dal versionamento.

## 2026-02-17 10:43:29
- Operazione: update
- File: src/backend/README.md
- Motivo: istruzioni setup config API key
- Dettagli: documentata procedura di copia .env.example e configurazione chiavi.

## 2026-02-17 10:43:29
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate le scritture per introduzione file di configurazione backend.

## 2026-02-17 10:44:28
- Operazione: update
- File: src/backend/README.md
- Motivo: correzione testo documentazione
- Dettagli: aggiornata frase su .env ignorato da git.

## 2026-02-17 10:44:28
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrata correzione testuale in README backend.

## 2026-02-17 10:49:20
- Operazione: update
- File: src/backend/app/models.py
- Motivo: supporto risposta ingest prezzi
- Dettagli: aggiunti modelli PriceRefreshItem e PriceRefreshResponse.

## 2026-02-17 10:49:20
- Operazione: update
- File: src/backend/app/config.py
- Motivo: configurazione provider realtime
- Dettagli: aggiunto parametro inance_request_timeout_seconds.

## 2026-02-17 10:49:20
- Operazione: create
- File: src/backend/app/finance_client.py
- Motivo: integrazione API provider finanziario
- Dettagli: creato client Twelve Data con parsing quote e gestione errori provider.

## 2026-02-17 10:49:20
- Operazione: update
- File: src/backend/app/repository.py
- Motivo: persistenza tick e selezione asset da aggiornare
- Dettagli: aggiunti metodi get_assets_for_price_refresh e save_price_tick con supporto mapping sset_provider_symbols.

## 2026-02-17 10:49:20
- Operazione: create
- File: src/backend/app/pricing_service.py
- Motivo: orchestrazione ingest prezzi
- Dettagli: creato servizio PriceIngestionService per fetch quote provider e salvataggio in price_ticks.

## 2026-02-17 10:49:20
- Operazione: update
- File: src/backend/app/main.py
- Motivo: esposizione endpoint ingest realtime
- Dettagli: aggiunto endpoint POST /prices/refresh.

## 2026-02-17 10:49:20
- Operazione: update
- File: src/backend/requirements.txt
- Motivo: dipendenza client HTTP provider
- Dettagli: aggiunta dipendenza httpx.

## 2026-02-17 10:49:20
- Operazione: update
- File: src/backend/.env.example
- Motivo: template configurazione ingest
- Dettagli: aggiunta variabile FINANCE_REQUEST_TIMEOUT_SECONDS.

## 2026-02-17 10:49:20
- Operazione: update
- File: src/backend/README.md
- Motivo: documentazione integrazione provider realtime
- Dettagli: aggiunto endpoint POST /prices/refresh e istruzioni di configurazione relative.

## 2026-02-17 10:49:20
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate modifiche per integrazione provider finanziario realtime.

## 2026-02-17 10:53:10
- Operazione: update
- File: src/backend/app/finance_client.py
- Motivo: resilienza chiamate provider realtime
- Dettagli: aggiunti retry su timeout/network/status 429-5xx, backoff esponenziale, supporto header Retry-After e logging tentativi.

## 2026-02-17 10:53:10
- Operazione: update
- File: src/backend/app/config.py
- Motivo: parametri resilienza ingest
- Dettagli: aggiunte impostazioni inance_max_retries, inance_retry_backoff_seconds, inance_symbol_request_delay_seconds.

## 2026-02-17 10:53:10
- Operazione: update
- File: src/backend/app/pricing_service.py
- Motivo: hardening ingest prezzi
- Dettagli: introdotti log start/end refresh, log errore per simbolo e delay configurabile tra richieste provider.

## 2026-02-17 10:53:10
- Operazione: update
- File: src/backend/app/main.py
- Motivo: visibilita operativa log backend
- Dettagli: aggiunta configurazione logging base per esecuzione locale.

## 2026-02-17 10:53:10
- Operazione: update
- File: src/backend/.env.example
- Motivo: configurazione resilienza provider
- Dettagli: aggiunte variabili FINANCE_MAX_RETRIES, FINANCE_RETRY_BACKOFF_SECONDS, FINANCE_SYMBOL_REQUEST_DELAY_SECONDS.

## 2026-02-17 10:53:10
- Operazione: update
- File: src/backend/README.md
- Motivo: documentazione retry/rate-limit
- Dettagli: documentati nuovi parametri e comportamento di resilienza dell'endpoint POST /prices/refresh.

## 2026-02-17 10:53:10
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate modifiche per stabilizzazione ingest realtime (retry/backoff/rate-limit/logging).

## 2026-02-17 10:56:09
- Operazione: update
- File: src/backend/app/config.py
- Motivo: configurazione refresh automatico prezzi
- Dettagli: aggiunte variabili price_scheduler_enabled, price_scheduler_interval_seconds, price_scheduler_portfolio_id.

## 2026-02-17 10:56:09
- Operazione: create
- File: src/backend/app/scheduler.py
- Motivo: automazione ingest realtime
- Dettagli: creato scheduler periodico con APScheduler per chiamare efresh_prices in background.

## 2026-02-17 10:56:09
- Operazione: update
- File: src/backend/requirements.txt
- Motivo: dipendenza scheduler
- Dettagli: aggiunta dipendenza pscheduler.

## 2026-02-17 10:56:09
- Operazione: update
- File: src/backend/app/main.py
- Motivo: lifecycle app con job automatico
- Dettagli: integrato scheduler nel lifespan FastAPI con start/stop automatico.

## 2026-02-17 10:56:09
- Operazione: update
- File: src/backend/.env.example
- Motivo: template configurazione scheduler
- Dettagli: aggiunte variabili PRICE_SCHEDULER_ENABLED, PRICE_SCHEDULER_INTERVAL_SECONDS, PRICE_SCHEDULER_PORTFOLIO_ID.

## 2026-02-17 10:56:09
- Operazione: update
- File: src/backend/README.md
- Motivo: documentazione scheduler prezzi
- Dettagli: aggiunte istruzioni per abilitare e configurare il refresh automatico.

## 2026-02-17 10:56:09
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate le modifiche per introduzione scheduler automatico prezzi.

## 2026-02-17 11:01:53
- Operazione: update
- File: src/backend/app/models.py
- Motivo: supporto endpoint storico giornaliero
- Dettagli: aggiunti modelli DailyBackfillItem, FxBackfillItem, DailyBackfillResponse.

## 2026-02-17 11:01:53
- Operazione: update
- File: src/backend/app/finance_client.py
- Motivo: ingest storico prezzi e cambi
- Dettagli: aggiunti metodi get_daily_bars e get_daily_fx_rates con parser dei dati giornalieri provider.

## 2026-02-17 11:01:53
- Operazione: update
- File: src/backend/app/repository.py
- Motivo: timeseries 1Y reale + persistenza daily
- Dettagli: get_timeseries ora calcola serie reale da 	ransactions, price_bars_1d, x_rates_1d; aggiunti upsert upsert_price_bar_1d e upsert_fx_rate_1d.

## 2026-02-17 11:01:53
- Operazione: create
- File: src/backend/app/historical_service.py
- Motivo: orchestrazione backfill storico
- Dettagli: creato servizio HistoricalIngestionService per backfill daily prezzi/FX su range configurabile.

## 2026-02-17 11:01:53
- Operazione: update
- File: src/backend/app/main.py
- Motivo: esposizione API storico giornaliero
- Dettagli: aggiunto endpoint POST /prices/backfill-daily e wiring servizio storico.

## 2026-02-17 11:01:53
- Operazione: update
- File: src/backend/README.md
- Motivo: documentazione nuovo flusso storico 1Y
- Dettagli: documentati endpoint POST /prices/backfill-daily e logica timeseries reale.

## 2026-02-17 11:01:53
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate modifiche per implementazione punto 3 (storico daily + timeseries reale).

## 2026-02-17 11:18:49
- Operazione: update
- File: src/backend/app/models.py
- Motivo: estensione contratti API e validazioni
- Dettagli: aggiunti modelli anagrafica asset, modello errore uniforme e vincoli più stretti su campi business (side/currency/type).

## 2026-02-17 11:18:49
- Operazione: create
- File: src/backend/app/errors.py
- Motivo: gestione errori coerente
- Dettagli: introdotta eccezione applicativa AppError con code/message/status_code.

## 2026-02-17 11:18:49
- Operazione: update
- File: src/backend/app/main.py
- Motivo: completamento API operative e qualità
- Dettagli: aggiunti endpoint POST /assets, GET /assets/{id}, POST /asset-provider-symbols; introdotti handler errore uniforme e idempotenza (Idempotency-Key) su refresh/backfill.

## 2026-02-17 11:18:49
- Operazione: update
- File: src/backend/app/repository.py
- Motivo: supporto persistenza anagrafica/idempotenza/performance
- Dettagli: aggiunti metodi CRUD asset+mapping provider, batch upsert daily (price_bars_1d, x_rates_1d) e metodi storage/lookup chiavi idempotenza.

## 2026-02-17 11:18:49
- Operazione: update
- File: src/backend/app/historical_service.py
- Motivo: ottimizzazione backfill storico
- Dettagli: sostituito upsert row-by-row con batch upsert per prezzi daily e FX daily.

## 2026-02-17 11:18:49
- Operazione: update
- File: database/schema.sql
- Motivo: tuning schema operativo
- Dettagli: aggiunti indici performance su transazioni/prezzi/FX e tabella pi_idempotency_keys.

## 2026-02-17 11:18:49
- Operazione: update
- File: database/seed.sql
- Motivo: bootstrap anagrafiche minime
- Dettagli: aggiunti seed asset iniziali (AAPL, MSFT, VWCE) e mapping provider 	welvedata.

## 2026-02-17 11:18:49
- Operazione: create
- File: database/migrations/20260217_01_operational_updates.sql
- Motivo: migrazione incrementale
- Dettagli: introdotti script non distruttivi per indici performance e tabella idempotenza su ambienti esistenti.

## 2026-02-17 11:18:49
- Operazione: create
- File: src/backend/Dockerfile
- Motivo: operativita container backend
- Dettagli: definita immagine runtime FastAPI per profilo prod/dev.

## 2026-02-17 11:18:49
- Operazione: create
- File: docker-compose.yml
- Motivo: orchestrazione locale/dev-prodlike
- Dettagli: aggiunti servizi db, pi-dev, pi-prod con profili separati.

## 2026-02-17 11:18:49
- Operazione: update
- File: scripts/bootstrap_db.ps1
- Motivo: bootstrap DB completo
- Dettagli: aggiunta applicazione automatica delle migrazioni oltre a schema e seed.

## 2026-02-17 11:18:49
- Operazione: create
- File: scripts/run_backend.ps1
- Motivo: avvio rapido backend locale
- Dettagli: script con setup venv, install dipendenze e run uvicorn.

## 2026-02-17 11:18:49
- Operazione: create
- File: src/backend/requirements-dev.txt
- Motivo: dipendenze test non-E2E
- Dettagli: aggiunto profilo dev con pytest.

## 2026-02-17 11:18:49
- Operazione: create
- File: src/backend/pytest.ini
- Motivo: configurazione test runner
- Dettagli: definiti 	estpaths e pythonpath per esecuzione coerente dei test backend.

## 2026-02-17 11:18:49
- Operazione: update
- File: src/backend/.gitignore
- Motivo: igiene workspace test
- Dettagli: aggiunta esclusione .pytest_cache.

## 2026-02-17 11:18:49
- Operazione: create
- File: src/backend/tests/unit/test_pricing_service.py
- Motivo: copertura unit ingest realtime
- Dettagli: test unit su PriceIngestionService con fake repo/client.

## 2026-02-17 11:18:49
- Operazione: create
- File: src/backend/tests/unit/test_historical_service.py
- Motivo: copertura unit backfill storico
- Dettagli: test unit su HistoricalIngestionService con verifica batch upsert prezzi/FX.

## 2026-02-17 11:18:49
- Operazione: create
- File: src/backend/tests/integration/test_api_behavior.py
- Motivo: copertura integration API behavior
- Dettagli: test su error model uniforme e fallback idempotente di POST /prices/refresh.

## 2026-02-17 11:18:49
- Operazione: update
- File: src/backend/README.md
- Motivo: allineamento documentazione backend
- Dettagli: aggiornati endpoint, error model, idempotenza, docker, script operativi e test.

## 2026-02-17 11:18:49
- Operazione: update
- File: README.md
- Motivo: allineamento documentazione root progetto
- Dettagli: aggiornato stato implementazione piano 3-7, run rapido e profili docker.

## 2026-02-17 11:18:49
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate tutte le scritture del ciclo completo (anagrafiche, qualità/idempotenza, performance, operativita, test).

## 2026-02-17 11:21:42
- Operazione: create
- File: docs/TEST_PLAN.md
- Motivo: pianificazione test backend deferred
- Dettagli: aggiunta checklist completa per validazione BE in ambiente con accesso completo (setup, test suite, smoke API, DB checks, idempotenza, scheduler, criteri di uscita).

## 2026-02-17 11:21:42
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrata creazione del piano test backend deferred.

## 2026-02-17 11:24:07
- Operazione: update
- File: .git/
- Motivo: inizializzazione repository versione codice
- Dettagli: eseguito git init nella root Valore365 per abilitare commit e pubblicazione su GitHub.

## 2026-02-17 11:24:07
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrata inizializzazione repository git locale.
