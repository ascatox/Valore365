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

## 2026-02-17 11:41:10
- Operazione: update
- File: docs/TEST_PLAN.md
- Motivo: tracciamento attivita pendenti
- Dettagli: aggiunto TODO operativo per push commit locale c650a7 su GitHub quando l'accesso sara disponibile.

## 2026-02-17 11:41:10
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrato aggiornamento TODO GitHub nel piano test.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/package.json
- Motivo: bootstrap frontend React + Vite
- Dettagli: definito progetto FE con script dev/build/preview e dipendenze React/TypeScript/Vite.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/.gitignore
- Motivo: igiene repository frontend
- Dettagli: esclusi 
ode_modules, dist e .env dal versionamento.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/.env.example
- Motivo: configurazione ambiente frontend
- Dettagli: aggiunte variabili VITE_API_BASE_URL e VITE_DEFAULT_PORTFOLIO_ID.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/index.html
- Motivo: entrypoint Vite
- Dettagli: aggiunto template HTML base con mount #root.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/tsconfig.json
- Motivo: configurazione TypeScript frontend
- Dettagli: abilitata configurazione strict e target compatibile con Vite.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/vite.config.ts
- Motivo: configurazione tooling frontend
- Dettagli: configurato plugin React e server dev su porta 5173.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/src/types.ts
- Motivo: tipizzazione contratti API frontend
- Dettagli: aggiunti tipi PortfolioSummary, Position, TimeSeriesPoint.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/src/api.ts
- Motivo: integrazione frontend-backend
- Dettagli: implementate chiamate fetch per summary, positions e timeseries con gestione errori.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/src/main.tsx
- Motivo: bootstrap app React
- Dettagli: configurato mount React StrictMode e import stili globali.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/src/App.tsx
- Motivo: dashboard iniziale frontend
- Dettagli: implementata vista KPI, stato caricamento/errore, sezione andamento 1Y e tabella posizioni.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/src/styles.css
- Motivo: identita visuale iniziale frontend
- Dettagli: aggiunti layout responsive, cards KPI e stile dashboard base.

## 2026-02-17 11:55:53
- Operazione: create
- File: src/frontend/README.md
- Motivo: documentazione avvio frontend
- Dettagli: aggiunti setup, variabili ambiente, stato attuale e prossimo step grafici.

## 2026-02-17 11:55:53
- Operazione: update
- File: README.md
- Motivo: allineamento documentazione root
- Dettagli: aggiunta sezione "Frontend stato attuale" con sintesi bootstrap React+Vite.

## 2026-02-17 11:55:53
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate tutte le scritture effettuate per avvio frontend React + Vite.

## 2026-02-17 11:58:02
- Operazione: update
- File: src/frontend/src/App.tsx
- Motivo: introduzione grafici dashboard frontend
- Dettagli: aggiunti line chart SVG per andamento 1Y e bar chart allocazione top posizioni basati su 	imeseries e positions.

## 2026-02-17 11:58:02
- Operazione: update
- File: src/frontend/src/styles.css
- Motivo: stile grafici frontend
- Dettagli: aggiunte classi per rendering line chart (chart-wrap, line-path) e allocation bars (ar-list, ar-track, ar-fill).

## 2026-02-17 11:58:02
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate modifiche per primo inserimento grafici nella dashboard frontend.

## 2026-02-17 12:00:39
- Operazione: update
- File: src/frontend/src/App.tsx
- Motivo: estensione grafico dashboard
- Dettagli: aggiunti switch periodo (1M, 3M, YTD, 1Y), assi/etichette nel line chart SVG e tooltip hover con crosshair e valore punto.

## 2026-02-17 12:00:39
- Operazione: update
- File: src/frontend/src/styles.css
- Motivo: stile interazioni grafico
- Dettagli: aggiunte classi per range switch, griglia assi, label, tooltip hover e overlay cattura mouse.

## 2026-02-17 12:00:39
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate modifiche per completare le 3 richieste grafico frontend (assi/tooltip/switch periodo).

## 2026-02-17 12:01:49
- Operazione: update
- File: src/frontend/src/App.tsx
- Motivo: miglioramento leggibilita KPI e chart
- Dettagli: aggiunta formattazione valuta/percentuale locale (Intl.NumberFormat), colorazione dinamica profit/loss nei KPI e mini-legenda del grafico.

## 2026-02-17 12:01:49
- Operazione: update
- File: src/frontend/src/styles.css
- Motivo: supporto visuale nuovi elementi dashboard
- Dettagli: aggiunte classi 	one-positive/	one-negative e stili legenda grafico (chart-legend, legend-dot).

## 2026-02-17 12:01:49
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate modifiche per formattazione valuta locale, colori dinamici KPI e mini-legenda grafico.

## 2026-02-17 12:09:28
- Operazione: update
- File: src/frontend/src/types.ts
- Motivo: supporto operazioni anagrafiche da frontend
- Dettagli: aggiunti tipi request/response per creazione asset, mapping provider e transazioni.

## 2026-02-17 12:09:28
- Operazione: update
- File: src/frontend/src/api.ts
- Motivo: integrazione API write dal frontend
- Dettagli: aggiunti helper postJson e funzioni createAsset, createAssetProviderSymbol, createTransaction.

## 2026-02-17 12:09:28
- Operazione: update
- File: src/frontend/src/App.tsx
- Motivo: inserimento rapido titoli da FE
- Dettagli: aggiunto pannello "Aggiungi Titolo Rapido" con submit unico (asset + provider symbol + buy opzionale) e refresh dashboard post-inserimento.

## 2026-02-17 12:09:28
- Operazione: update
- File: src/frontend/src/styles.css
- Motivo: stile form rapido frontend
- Dettagli: aggiunte classi per layout form, input/select, bottone primario e stato successo/errore.

## 2026-02-17 12:09:28
- Operazione: update
- File: src/frontend/README.md
- Motivo: documentazione flusso rapido FE
- Dettagli: aggiunta sezione su creazione titolo da frontend con chiamate API coinvolte.

## 2026-02-17 12:09:28
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate modifiche per implementazione inserimento rapido titoli da frontend.

## 2026-02-17 12:17:37
- Operazione: update
- File: src/frontend/src/types.ts
- Motivo: supporto autocomplete e write API frontend
- Dettagli: aggiunto tipo AssetSearchItem e tipi request per asset/provider/transazioni.

## 2026-02-17 12:17:37
- Operazione: update
- File: src/frontend/src/api.ts
- Motivo: estensione integrazione API frontend
- Dettagli: aggiunti postJson, searchAssets, createAsset, createAssetProviderSymbol, createTransaction.

## 2026-02-17 12:17:37
- Operazione: update
- File: src/frontend/src/App.tsx
- Motivo: inserimento titoli FE piu veloce
- Dettagli: aggiunti autocomplete symbol da /assets/search, selezione titolo esistente e validazioni client-side (symbol/currency/isin/exchange/buy).

## 2026-02-17 12:17:37
- Operazione: update
- File: src/frontend/src/styles.css
- Motivo: UI autocomplete frontend
- Dettagli: aggiunti stili lista suggerimenti (suggestions, suggestion-item) e supporto visuale campo ricerca.

## 2026-02-17 12:17:37
- Operazione: update
- File: src/frontend/README.md
- Motivo: documentazione UX rapido inserimento titoli
- Dettagli: aggiunte note su autocomplete asset esistenti e validazione client-side.

## 2026-02-17 12:17:37
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate modifiche del nuovo flusso rapido FE con autocomplete e validazioni.

## 2026-02-17 12:22:59
- Operazione: update
- File: src/frontend/src/types.ts
- Motivo: supporto nuovi flussi operativi dashboard
- Dettagli: aggiunti tipi PriceRefreshResponse e DailyBackfillResponse.

## 2026-02-17 12:22:59
- Operazione: update
- File: src/frontend/src/api.ts
- Motivo: azioni FE su endpoint ingest
- Dettagli: aggiunte funzioni efreshPrices e ackfillDaily oltre all'estensione API search/insert già presente.

## 2026-02-17 12:22:59
- Operazione: update
- File: src/frontend/src/App.tsx
- Motivo: completamento richieste operative FE in sequenza
- Dettagli: aggiunti pulsanti Refresh prezzi ora e Backfill 1Y, introduzione toast notifications (success/error/info) con auto-dismiss e rimozione dei messaggi statici di esito form.

## 2026-02-17 12:22:59
- Operazione: update
- File: src/frontend/src/styles.css
- Motivo: supporto UI operazioni e toast
- Dettagli: aggiunti stili per pannello operazioni, bottoni secondari e stack toast responsive.

## 2026-02-17 12:22:59
- Operazione: update
- File: src/frontend/README.md
- Motivo: documentazione funzionalita FE aggiuntive
- Dettagli: documentati pulsanti refresh/backfill e sistema notifiche toast.

## 2026-02-17 12:22:59
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate modifiche per implementazione dei 3 step richiesti in sequenza (refresh, backfill, toast).

## 2026-02-17 12:38:25
- Operazione: update
- File: src/backend/app/config.py
- Motivo: configurazione auth esterna veloce
- Dettagli: aggiunte variabili Clerk (clerk_auth_enabled, clerk_jwks_url, clerk_authorized_parties) e parser lista parti autorizzate.

## 2026-02-17 12:38:25
- Operazione: create
- File: src/backend/app/auth.py
- Motivo: protezione API backend con provider OAuth esterno
- Dettagli: implementata validazione JWT Clerk via JWKS con cache, estrazione bearer token e dependency equire_auth.

## 2026-02-17 12:38:25
- Operazione: update
- File: src/backend/app/main.py
- Motivo: enforcement accessi backend
- Dettagli: aggiunta dependency equire_auth su tutte le route applicative (tranne /health).

## 2026-02-17 12:38:25
- Operazione: update
- File: src/backend/requirements.txt
- Motivo: dipendenze verifica token JWT
- Dettagli: aggiunte dipendenze PyJWT e cryptography.

## 2026-02-17 12:38:25
- Operazione: update
- File: src/backend/.env.example
- Motivo: setup ambiente auth Clerk backend
- Dettagli: aggiunte variabili CLERK_AUTH_ENABLED, CLERK_JWKS_URL, CLERK_AUTHORIZED_PARTIES.

## 2026-02-17 12:38:25
- Operazione: update
- File: src/backend/README.md
- Motivo: documentazione integrazione auth veloce
- Dettagli: aggiunta sezione "Auth (Clerk - soluzione veloce)" con configurazione e comportamento route protette.

## 2026-02-17 12:38:25
- Operazione: update
- File: src/frontend/package.json
- Motivo: dipendenza login provider esterno
- Dettagli: aggiunta dipendenza @clerk/clerk-react.

## 2026-02-17 12:38:25
- Operazione: update
- File: src/frontend/.env.example
- Motivo: configurazione frontend auth Clerk
- Dettagli: aggiunta variabile VITE_CLERK_PUBLISHABLE_KEY.

## 2026-02-17 12:38:25
- Operazione: update
- File: src/frontend/src/main.tsx
- Motivo: bootstrap auth frontend
- Dettagli: integrato ClerkProvider con validazione presenza publishable key.

## 2026-02-17 12:38:25
- Operazione: update
- File: src/frontend/src/api.ts
- Motivo: propagazione token auth verso backend
- Dettagli: estesi helper API con header Authorization: Bearer <token> e supporto token su tutte le chiamate.

## 2026-02-17 12:38:25
- Operazione: update
- File: src/frontend/src/App.tsx
- Motivo: login/guard FE e chiamate protette
- Dettagli: aggiunti SignedOut/SignIn, SignedIn, UserButton, recupero token Clerk (getToken) e uso token su fetch dashboard/operazioni.

## 2026-02-17 12:38:25
- Operazione: update
- File: src/frontend/src/styles.css
- Motivo: supporto UI login Clerk
- Dettagli: aggiunti stili uth-shell, uth-card, 	opbar-actions per schermata accesso e barra utente.

## 2026-02-17 12:38:25
- Operazione: update
- File: src/frontend/README.md
- Motivo: documentazione setup login frontend
- Dettagli: aggiunte note su VITE_CLERK_PUBLISHABLE_KEY e pagina login Clerk.

## 2026-02-17 12:38:25
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrata integrazione Clerk come soluzione piu veloce per gestione accessi FE+BE.

## 2026-02-17 13:09:38
- Operazione: update
- File: src/frontend/src/App.tsx
- Motivo: refactor frontend con componentizzazione
- Dettagli: App.tsx ridotto a orchestrazione stato/auth e wiring dei componenti UI.

## 2026-02-17 13:09:38
- Operazione: create
- File: src/frontend/src/components/atoms/Panel.tsx
- Motivo: introdurre componente atomico contenitore
- Dettagli: aggiunto componente Panel riutilizzabile con titolo opzionale.

## 2026-02-17 13:09:38
- Operazione: create
- File: src/frontend/src/components/atoms/Button.tsx
- Motivo: introdurre componente atomico bottone
- Dettagli: aggiunto componente Button con varianti primary/secondary/range.

## 2026-02-17 13:09:38
- Operazione: create
- File: src/frontend/src/components/feedback/toast-types.ts
- Motivo: centralizzazione tipi notifiche
- Dettagli: definiti ToastKind e ToastItem condivisi tra App e UI toast.

## 2026-02-17 13:09:38
- Operazione: create
- File: src/frontend/src/components/feedback/ToastStack.tsx
- Motivo: estrazione rendering notifiche
- Dettagli: spostata visualizzazione toast in componente dedicato.

## 2026-02-17 13:09:38
- Operazione: create
- File: src/frontend/src/components/operations/OpsPanel.tsx
- Motivo: separazione pannello azioni operative
- Dettagli: estratti pulsanti refresh prezzi e backfill 1Y in componente dedicato.

## 2026-02-17 13:09:38
- Operazione: create
- File: src/frontend/src/components/forms/QuickAddForm.tsx
- Motivo: separazione flusso di inserimento rapido titoli
- Dettagli: spostate logica form, autocomplete, validazioni e submit API dal componente App.

## 2026-02-17 13:09:38
- Operazione: create
- File: src/frontend/src/components/charts/PortfolioLineChart.tsx
- Motivo: separazione rendering e logica grafico
- Dettagli: estratti range switch, calcolo modello SVG e tooltip hover del grafico andamento.

## 2026-02-17 13:09:38
- Operazione: create
- File: src/frontend/src/components/dashboard/KpiGrid.tsx
- Motivo: separazione card KPI
- Dettagli: estratto rendering KPI valore totale, P/L e delta 1Y.

## 2026-02-17 13:09:38
- Operazione: create
- File: src/frontend/src/components/dashboard/AllocationBars.tsx
- Motivo: separazione sezione allocazione
- Dettagli: estratto bar chart top posizioni con calcolo pesi percentuali.

## 2026-02-17 13:09:38
- Operazione: create
- File: src/frontend/src/components/dashboard/PositionsTable.tsx
- Motivo: separazione tabella posizioni
- Dettagli: estratto rendering tabellare delle posizioni portfolio.


## 2026-02-17 13:11:02
- Operazione: update
- File: WRITE_LOG.md
- Motivo: tracciamento operazioni di scrittura
- Dettagli: registrate le modifiche di refactor FE con estrazione componenti atomici e sezioni dashboard fuori da App.tsx.


## 2026-02-24 Smoke Test MVP (Checklist Manuale)
- Prerequisiti: DB PostgreSQL attivo, backend FastAPI avviato, frontend avviato.
- Seleziona o crea un portfolio dalla pagina `Portfolio`.
- Clicca `Nuova Transazione`.
- Cerca un asset con discover (es. `AAPL`), selezionalo e salva un `BUY`.
- Inserisci un secondo `BUY` sullo stesso asset con prezzo diverso.
- Inserisci un `SELL` con quantita inferiore alla posizione aperta.
- Verifica in `Portfolio`: storico con 3 righe ordinate per data desc.
- Verifica in `Portfolio`: delete rimuove una riga e aggiorna la tabella.
- Verifica in `Portfolio`: modifica aggiorna quantita/prezzo/note della riga.
- Verifica in `Dashboard`: sezione `Portfolio Tracker (MVP)` con KPI valorizzati.
- Verifica in `Dashboard`: tabella posizioni con almeno una posizione e P/L coerente.
- Verifica in `Dashboard`: tabella allocazione reale con pesi > 0.
- Caso errore: modifica una `SELL` con quantita eccessiva e verifica messaggio `Quantita insufficiente per sell`.
- Note esecuzione: annotare bug residui, endpoint coinvolti, screenshot se utili.

## 2026-02-24 Smoke Test MVP (Esito Eseguito)
- Stack dev avviato con `docker compose --profile dev up --build -d`.
- Servizi verificati attivi: `valore365-db`, `valore365-api-dev`, `valore365-frontend`.
- Health backend verificato: `GET /api/health` -> `{"status":"ok"}`.
- Frontend verificato raggiungibile su `http://localhost:8080` (HTTP 200).
- Creato portfolio smoke test: `id=7` (`Smoke Portfolio 20260224`).
- Creato asset locale smoke test: `SMKTEST26` (`id=19`).
- Create transazioni eseguite: `BUY`, `BUY`, `SELL` (OK).
- Verifiche endpoint OK: `GET /portfolios/7/transactions`, `positions`, `summary`, `allocation`.
- Verificato `PATCH /transactions/{id}` (OK) e caso errore `sell` eccessiva -> `400 bad_request` con messaggio corretto.
- Verificato `DELETE /transactions/{id}` (OK) con ricalcolo corretto di storico/posizioni/summary/allocation.
- Stato finale portfolio smoke: 2 transazioni, posizione residua `7`, `avg_cost=100.1`, `market_value=700.7`, allocazione `100%`.
