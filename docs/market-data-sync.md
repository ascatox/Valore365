# Sincronizzazione dei dati di mercato (TASK-54)

I prezzi del portafoglio (quotazioni, chiusure giornaliere, cambi) vengono aggiornati da **una sola
procedura**, `MarketDataSyncService.run_sync` (`src/backend/app/services/market_data_sync.py`), che può
partire da quattro inneschi:

| Innesco (`trigger`) | Quando |
|---|---|
| `external` | GitHub Actions (`.github/workflows/market-data-sync.yml`): lun-ven 22:40 UTC e mar-sab 06:15 UTC, o a mano |
| `startup` | all'avvio del backend, in background, se l'ultima sincronizzazione riuscita è precedente all'ultima seduta conclusa |
| `scheduler` | job giornaliero interno delle barre (`DAILY_BARS_SCHEDULER_*`), se l'istanza è sveglia |
| `manual` | riservato a chiamate dirette del servizio (script, shell) |

Lo scheduler interno da solo non basta: su Render l'istanza può essere sospesa e il job salta. Un
aggiornamento mancato si recupera al successivo avvio o al successivo trigger esterno.

## Come funziona

1. **Un solo aggiornamento alla volta.** La run prende un lock di processo e poi un lock di database
   (`pg_try_advisory_xact_lock`) su una connessione dedicata, tenuta in transazione per tutta la run e
   chiusa nel `finally`. Se il lock è occupato il secondo innesco riceve "già in corso" (`409` per
   l'endpoint) e non parte una seconda sincronizzazione. La variante *xact* funziona anche dietro il
   pooler di Supabase in transaction mode e si libera da sola se la connessione cade. È l'unica
   connessione tenuta durante le chiamate di rete (una in più rispetto al pool usato dalle richieste).
2. **Passi** (registro estendibile con `register_step`, per esempio per i dati ETF o i metadati):
   - `quotes`: quotazioni di tutti gli asset attivi in portafoglio (transazioni o target, tutti i
     portafogli). *Best effort*: un errore qui viene registrato ma non decide l'esito, perché il dato di
     riferimento è la chiusura giornaliera;
   - `bars`: barre giornaliere dall'ultima barra salvata dell'asset più indietro, con un limite di
     `MARKET_DATA_SYNC_MAX_LOOKBACK_DAYS` giorni (minimo 5);
   - `fx`: cambi giornalieri delle valute in uso (valuta di acquisto o di quotazione → valuta base del
     portafoglio), stessa finestra, stessa validazione del backfill esistente.
3. **Stato persistente** (migrazione `database/migrations/20261103_01_market_data_sync.sql`):
   - `market_data_sync_runs`: una riga per run con `trigger`, `status` (`running`, `success`, `partial`,
     `failed`), orari, passi (`steps` jsonb con conteggi ed errori), asset richiesti/aggiornati/in
     ritardo, errore;
   - `market_data_asset_sync`: per asset ultima barra, ultimo tick, ultimo successo, ultimo errore.
4. **Esito.** `success` solo se ogni asset prezzabile ha la barra dell'**ultima seduta conclusa della
   sua borsa** e nessun passo bloccante (`bars`, `fx`) ha errori. `failed` se un passo bloccante
   fallisce del tutto o nessun asset è aggiornato; altrimenti `partial`.
   `last_successful_price_sync` è la fine dell'ultima run `success`: **una run parziale o fallita non
   lo sposta**, mentre lo stato per asset avanza comunque. Una run rimasta `running` per un processo
   terminato viene chiusa come `failed` alla run successiva.
5. **Calendari per borsa.** Le sedute vengono da `services/market_hours.py` (suffisso Yahoo del
   simbolo): weekend e principali festività (NYSE, borse europee, Ferragosto per Milano) non sono sedute
   mancate. Una seduta conta come conclusa dopo la chiusura più `MARKET_DATA_SYNC_GRACE_MINUTES` (il
   provider pubblica la barra con qualche minuto di ritardo). Gli asset con solo ISIN (nessun simbolo
   Yahoo) sono esclusi dalla verifica e elencati come `skipped_symbols`.
6. **Quando serve una sincronizzazione** (`needs_sync`): nessuna run riuscita, oppure l'ultima riuscita
   è precedente all'ultima chiusura (+ margine) fra le borse degli asset in portafoglio, oppure un asset
   è indietro rispetto alla propria ultima seduta e non è stato tentato dopo quella chiusura. All'avvio
   c'è anche una pausa di 3 ore dall'ultima run terminata, così un asset che il provider non aggiorna più
   non fa ripartire una run a ogni risveglio dell'istanza.

## Endpoint interni

Fuori dallo schema OpenAPI, autenticati con `Authorization: Bearer <MARKET_DATA_SYNC_TOKEN>` (confronto
a tempo costante). Senza token configurato rispondono `404` (disattivati); token mancante o errato `401`.

| Endpoint | Risposte |
|---|---|
| `POST /api/internal/market-data/sync` | `202 {run_id, status: "running"}` (run avviata in background); `409 {code: "already_running", run_id}`; `200 {status: "up_to_date", last_successful_price_sync}` se non serve. `?force=true` esegue comunque |
| `GET /api/internal/market-data/sync/status` | ultima run (con i passi), run in corso, ultima riuscita, `needs_sync`, asset in ritardo (solo simbolo, ultima barra, sedute mancate, ultimo errore) |

Rate limit per IP (finestra 1 ora): `POST` 10, `status` 240, autenticazioni fallite 30 (un token valido
non viene mai bloccato dagli errori altrui). Le risposte contengono solo conteggi e simboli, mai dati
degli utenti.

## MCP

I tool che restituiscono valori aggiungono `data_freshness` (`last_successful_price_sync`,
`last_sync_status`, `last_sync_finished_at`, `stale_symbols`, `oldest_price_at`, `note`) e il tool
`get_data_freshness` dà il dettaglio per posizione: vedi [mcp.md](mcp.md#tool-disponibili).

## Setup (proprietario)

1. **Migrazione su Supabase.** SQL Editor → incollare ed eseguire
   `database/migrations/20261103_01_market_data_sync.sql` (idempotente: si può rieseguire). Il backend
   crea comunque le tabelle all'avvio se mancano; la migrazione esplicita attiva anche la RLS.
2. **Token.** Generare un valore casuale lungo, per esempio
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. **Render.** Dashboard → servizio `valore365-api` → Environment → `MARKET_DATA_SYNC_TOKEN` = il token
   (la voce è in `render.yaml` con `sync: false`). Salvare e attendere il redeploy.
4. **GitHub.** Repository → Settings → Secrets and variables → Actions → New repository secret:
   - `VALORE365_API_BASE_URL` = `https://valore365.onrender.com` (senza `/api` né `/` finale);
   - `MARKET_DATA_SYNC_TOKEN` = lo stesso token.
5. **Workflow.** Tab Actions → "Market Data Sync": se i workflow sono disattivati abilitarli; i cron
   partono dal ramo predefinito (`main`) dopo il merge. Avviarlo a mano con "Run workflow" (opzione
   `force` per eseguire anche se i dati risultano aggiornati).

## Verifica

- Nel job GitHub: passi "Wake up the API", "Trigger sync" (`HTTP 202` o `200 up_to_date`), "Wait for
  the sync to finish" con `status=success`; il riepilogo del job elenca passi e asset in ritardo. Il job
  fallisce se la run è `failed` (o il servizio non risponde in ~3 minuti), avvisa con un warning se è
  `partial`.
- Dal terminale (senza stampare il token nella cronologia):

  ```bash
  read -rs TOKEN
  curl -s -H "Authorization: Bearer $TOKEN" https://valore365.onrender.com/api/internal/market-data/sync/status | jq
  ```

- Nei log di Render: `market_data_sync started run_id=... trigger=external`,
  `market_data_sync finished run_id=... status=success`, all'avvio
  `market_data_sync startup catch-up: sync needed` oppure `data up to date`.
- In Supabase: `select id, trigger, status, started_at, finished_at, assets_updated, assets_failed, error
  from market_data_sync_runs order by id desc limit 10;`
- Da un client MCP: `get_data_freshness` con il `portfolio_id`.

## Parametri

| Variabile | Default | Descrizione |
|---|---|---|
| `MARKET_DATA_SYNC_TOKEN` | vuoto | Token degli endpoint interni; vuoto = disattivati (404) |
| `MARKET_DATA_SYNC_ON_STARTUP` | `true` | Recupero all'avvio in background |
| `MARKET_DATA_SYNC_MAX_LOOKBACK_DAYS` | `30` | Finestra massima di barre e cambi |
| `MARKET_DATA_SYNC_GRACE_MINUTES` | `60` | Minuti dopo la chiusura prima che una seduta conti come conclusa |
| `MARKET_DATA_SYNC_RATE_LIMIT_REQUESTS` / `MARKET_DATA_SYNC_STATUS_RATE_LIMIT_REQUESTS` / `MARKET_DATA_SYNC_AUTH_FAILURE_LIMIT_REQUESTS` / `MARKET_DATA_SYNC_RATE_LIMIT_WINDOW_SECONDS` | `10` / `240` / `30` / `3600` | Rate limit degli endpoint interni |

## Limiti noti

- Le festività sono quelle principali (approssimate per eccesso): una chiusura straordinaria non in
  calendario fa risultare un asset in ritardo per quella seduta (run `partial`, recuperata al giro dopo).
- Il lock di database è legato a una transazione aperta per tutta la run: se Postgres o il pooler
  impongono un `idle_in_transaction_session_timeout` più corto della durata di un passo, la connessione
  viene chiusa e il lock si libera prima della fine (tra un passo e l'altro la run esegue un `select 1`).
- I cron di GitHub Actions possono partire con qualche decina di minuti di ritardo: per questo c'è la
  seconda esecuzione del mattino.
