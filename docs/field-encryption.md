# Cifratura a livello di campo dei dati personali (TASK-57)

Il database (Postgres su Supabase) è già cifrato su disco da Supabase, ma chi ottiene la
`DATABASE_URL`, un dump o l'accesso alla dashboard legge tutto in chiaro. Il backend cifra
quindi **lato applicazione** i campi testuali personali, prima di scriverli nel database.

Cifrare tutte le colonne romperebbe le aggregazioni SQL (posizioni, riepiloghi, PAC,
performance) e non avrebbe senso per i dati di mercato pubblici: importi, quantità, prezzi,
date, ID e dati di mercato restano in chiaro.

## Cosa è cifrato

| Tabella | Colonna | Ricerca |
|---|---|---|
| `app_users` | `email` | `email_bidx`: blind index dell'email normalizzata (trim + minuscole) |
| `portfolios` | `name` | nessuna (l'ordinamento è per `created_at`, non per nome) |
| `transactions` | `notes` | nessuna |
| `csv_import_batches` | `original_filename` | `original_filename_bidx`: blind index del nome esatto |
| `csv_import_batches` | `preview_data` (jsonb) | `source_sha256` in colonna dedicata (hash del file, in chiaro) |
| `doctor_policy_sets` | `name` | nessuna |
| `tribunal_sessions` | `payload` (seduta del Tribunale in JSON, TASK-66) | nessuna (la ricerca è per `owner_user_id` + `scope_fingerprint` in chiaro) |

Le API restituiscono i valori in chiaro: i contratti non cambiano. La decifratura avviene nel
repository (`app/repository/*`, `app/services/doctor_policy/store.py`,
`app/services/tribunal/store.py`, `app/auth.py`), quindi
anche Copilot, MCP ed export vedono i valori in chiaro.

Il rilevamento degli import CSV duplicati, che prima leggeva `preview_data->>'source_sha256'`
e confrontava `original_filename` in SQL, usa ora `source_sha256` e `original_filename_bidx`.
Finché il backfill non è stato eseguito, le righe legacy senza blind index vengono ancora
confrontate per nome in chiaro.

## Come funziona

Codice: `src/backend/app/crypto/`.

- **Envelope encryption.** Ogni utente ha una DEK (chiave dati) casuale a 256 bit, salvata
  in `user_data_keys` cifrata con la KEK (chiave master) attiva: AES-256-GCM, nonce casuale
  di 12 byte, AAD `dek:<user_id>`. La DEK viene creata alla prima scrittura dell'utente, in
  una transazione propria (`insert ... on conflict do nothing` + rilettura, sicuro con
  richieste concorrenti) e tenuta in una cache in memoria (LRU, 1024 voci, TTL 10 minuti,
  `DATA_DEK_CACHE_SIZE` / `DATA_DEK_CACHE_TTL_SECONDS`).
- **Campi.** Ogni valore è cifrato con AES-256-GCM con la DEK del proprietario, nonce casuale
  di 12 byte e AAD `<tabella>:<colonna>:<owner_user_id>`: un valore copiato su un'altra
  colonna o un altro utente non si decifra. Formato salvato come testo:
  `enc:v1:<base64url(nonce || ciphertext)>`; per `preview_data` il jsonb è
  `{"_enc": "enc:v1:..."}`.
- **Valori legacy.** Un valore senza prefisso `enc:v1:` è testo in chiaro scritto prima della
  cifratura e viene restituito così com'è: la migrazione è progressiva.
- **Errori.** Un token alterato o con AAD sbagliata solleva `DecryptionError`; una DEK assente
  (utente crypto-shredded) o una KEK non più nel keyring solleva `KeyUnavailableError`
  (sottoclasse di `DecryptionError`).
- **Blind index.** HMAC-SHA256 con `DATA_BLIND_INDEX_KEY`, separato per colonna
  (`app_users.email`, `csv_import_batches.original_filename`). Deterministico: permette solo
  ricerche per **uguaglianza**, non per sottostringa né ordinamento.

## Configurazione

| Variabile | Valore |
|---|---|
| `DATA_ENCRYPTION_KEYS` | keyring `kid1:base64key,kid2:base64key`, chiavi di 32 byte; la **prima** è la KEK attiva (cifra le nuove DEK), le altre servono solo a decifrare le DEK create prima di una rotazione |
| `DATA_BLIND_INDEX_KEY` | base64 di 32 byte, chiave HMAC dei blind index |

- `APP_ENV=prod`/`production`: senza `DATA_ENCRYPTION_KEYS` o senza `DATA_BLIND_INDEX_KEY`
  **l'avvio fallisce** con un errore esplicito.
- dev/test: senza `DATA_ENCRYPTION_KEYS` i campi restano in chiaro (un warning nel log) e i
  blind index usano una chiave fissa di sviluppo, così le ricerche funzionano. I test non
  richiedono nessuna variabile.

Su Render le due variabili sono in `render.yaml` con `sync: false`: si impostano nel dashboard,
mai nel repository.

### Generare le chiavi

```bash
# KEK (il kid è libero: lettere, cifre, _ . -; conviene una data)
python3 -c "import base64, os; print('k202611:' + base64.b64encode(os.urandom(32)).decode())"
# chiave dei blind index
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

Conservare una copia delle chiavi fuori da Render (password manager / vault): **perdere la KEK
significa perdere tutti i dati cifrati**. `DATA_BLIND_INDEX_KEY` non va mai cambiata dopo il
primo deploy (i blind index esistenti smetterebbero di corrispondere; andrebbero ricalcolati).

## Ordine di deploy

1. **Migrazione**: applicare `database/migrations/20261108_01_field_encryption.sql` nel SQL
   editor di Supabase (crea `user_data_keys` con RLS attiva senza policy, aggiunge
   `email_bidx`, `original_filename_bidx`, `source_sha256` con gli indici, porta
   `app_users.email` a `text` e copia `source_sha256` dal jsonb esistente). È idempotente.
2. **Variabili**: impostare `DATA_ENCRYPTION_KEYS` e `DATA_BLIND_INDEX_KEY` su Render.
3. **Deploy** del backend. Da qui le nuove scritture sono cifrate e, all'avvio, il backend
   esegue da solo il **backfill** dei dati esistenti (sezione seguente): non serve nessuna
   shell. Finché il backfill non ha finito i dati legacy restano leggibili in chiaro.

L'ordine conta: un backend nuovo su un database senza migrazione fallisce su ogni scrittura
cifrata (`user_data_keys` mancante) e sugli import CSV (colonne mancanti).

## Backfill automatico all'avvio

Codice: `src/backend/app/services/field_encryption_backfill.py` (usa
`app/crypto/backfill.py`, lo stesso codice dello script).

- Parte a ogni avvio se `DATA_ENCRYPTION_KEYS` è configurata e `DATA_BACKFILL_ON_STARTUP`
  è attivo (default `true`), in un thread in background: l'avvio e il bind della porta non
  lo aspettano e un suo errore non blocca mai l'avvio (finisce nel log).
- Cifra i valori ancora in chiaro e riempie `email_bidx`, `original_filename_bidx` e
  `source_sha256`. È idempotente: a dati già cifrati fa solo una query per tabella e scrive
  una riga di riepilogo nel log (`field encryption backfill: completed, rows updated=0 ...`).
- Lavora a blocchi (`DATA_BACKFILL_BATCH_SIZE`, default 500 righe, una transazione per
  blocco) con una pausa tra un blocco e l'altro (`DATA_BACKFILL_BATCH_PAUSE_SECONDS`,
  default 0.2) per non occupare il pool di connessioni.
- Una sola istanza alla volta: `pg_try_advisory_xact_lock` su una connessione dedicata
  (come la sincronizzazione dei dati di mercato, variante "xact" per il pooler di Supabase
  in transaction mode). Con deploy sovrapposti la seconda istanza trova il lock occupato,
  lo scrive nel log e salta.
- Allo shutdown si ferma dopo il blocco corrente; il resto lo riprende l'avvio successivo.
- Una riga che non si riesce a cifrare viene registrata nel log e saltata; un errore di
  database su una tabella annulla solo il blocco corrente di quella tabella e il backfill
  passa alla tabella successiva. Le righe saltate vengono ritentate all'avvio successivo.
- Log (logger `app.services.field_encryption_backfill`): avvio, righe aggiornate per tabella
  (solo se ce ne sono), riepilogo con totale e durata, errori.
- Esito dell'ultima run del processo per gli admin: `GET /api/admin/field-encryption/backfill`
  (`status`: `running`, `completed`, `completed_with_errors`, `stopped`, `skipped_locked`,
  `failed`, `disabled`; `started_at`, `finished_at`, righe per tabella, `error`). È per
  istanza: quella che ha trovato il lock occupato risponde `skipped_locked`.
- Per disattivarlo: `DATA_BACKFILL_ON_STARTUP=false`.

### Verifica dal SQL Editor di Supabase

Righe ancora da cifrare per colonna (tutte a 0 = backfill completo):

```sql
select 'app_users.email' as colonna, count(*) as in_chiaro
  from app_users where email is not null and email not like 'enc:v1:%'
union all
select 'app_users.email_bidx mancante', count(*)
  from app_users where email is not null and email_bidx is null
union all
select 'portfolios.name', count(*)
  from portfolios where name is not null and name not like 'enc:v1:%'
union all
select 'transactions.notes', count(*)
  from transactions where notes is not null and notes not like 'enc:v1:%'
union all
select 'csv_import_batches.original_filename', count(*)
  from csv_import_batches where original_filename is not null and original_filename not like 'enc:v1:%'
union all
select 'csv_import_batches.original_filename_bidx mancante', count(*)
  from csv_import_batches where original_filename is not null and original_filename_bidx is null
union all
select 'csv_import_batches.preview_data', count(*)
  from csv_import_batches
  where preview_data is not null
    and not (jsonb_typeof(preview_data) = 'object' and preview_data ? '_enc')
union all
select 'doctor_policy_sets.name', count(*)
  from doctor_policy_sets where name is not null and name not like 'enc:v1:%'
union all
select 'tribunal_sessions.payload', count(*)
  from tribunal_sessions where payload is not null and payload not like 'enc:v1:%';
```

### Esecuzione manuale (script)

Lo script resta disponibile per esecuzioni manuali (dry run, una sola tabella) e per la
rotazione della KEK (`--rewrap-keys`), con le stesse variabili d'ambiente del backend
(`DATABASE_URL`, `DATA_ENCRYPTION_KEYS`, `DATA_BLIND_INDEX_KEY`, `APP_ENV`):

```bash
python scripts/encrypt_existing_data.py --dry-run     # conta le righe da aggiornare
python scripts/encrypt_existing_data.py               # cifra e riempie i blind index
python scripts/encrypt_existing_data.py --table portfolios --batch-size 200
```

Lo script è idempotente (salta i valori già cifrati), lavora a blocchi (una transazione per
blocco, `--batch-size`, default 500) e si può rieseguire o interrompere in qualsiasi
momento. Il `--dry-run` non scrive nulla, nemmeno le DEK. Non prende l'advisory lock: se
gira insieme al backfill automatico le due esecuzioni possono cifrare le stesse righe: il
risultato resta corretto (l'aggiornamento tocca solo righe ancora in chiaro), ma è lavoro
sprecato.

## Rotazione della KEK

Con l'envelope encryption i dati non vanno ricifrati: cambia solo la cifratura delle DEK.

1. Generare una nuova KEK e metterla **in testa** al keyring, lasciando la vecchia:
   `DATA_ENCRYPTION_KEYS=k202705:NUOVA,k202611:VECCHIA`. Deploy: le nuove DEK usano la nuova
   KEK, le vecchie DEK si decifrano ancora con la vecchia.
2. Ricifrare tutte le DEK con la KEK attiva:

   ```bash
   python scripts/encrypt_existing_data.py --rewrap-keys --dry-run
   python scripts/encrypt_existing_data.py --rewrap-keys
   ```

3. Quando `select kek_id, count(*) from user_data_keys group by 1` mostra solo la nuova KEK,
   togliere la vecchia dal keyring e rifare il deploy.

## Crypto-shredding (diritto all'oblio)

`app.crypto.shred_user_keys(conn, user_id)` cancella la riga di `user_data_keys` dell'utente e
invalida la cache: tutti i suoi valori cifrati diventano illeggibili, anche nei backup
successivi alla cifratura. Non è collegata a nessun endpoint. Va accompagnata dalla
cancellazione delle righe dell'utente (o almeno dei valori legacy in chiaro e dei blind index,
che lo shredding non tocca). Con più processi, un'altra istanza può tenere la DEK in cache fino
al TTL (10 minuti).

## Limiti

- **Backup precedenti**: i backup e i dump fatti prima della migrazione e del backfill
  contengono i dati in chiaro, e il crypto-shredding non li raggiunge.
- **Backend compromesso = chiavi esposte**: la KEK vive nelle variabili d'ambiente del backend.
  La cifratura protegge da chi ha solo il database (dump, `DATABASE_URL`, dashboard Supabase),
  non da chi controlla il backend o il dashboard di Render.
- **Niente ricerche SQL sui campi cifrati**: solo uguaglianza tramite blind index; nessun
  `LIKE`, ordinamento o raggruppamento per nome in SQL. Al momento nessuna query lo faceva.
- **Il blind index rivela le uguaglianze**: due righe con la stessa email (o lo stesso nome di
  file) hanno lo stesso indice.
- **Cambio di proprietario**: l'AAD contiene `owner_user_id`; spostare righe cifrate su un
  altro utente in SQL (come faceva `20260226_06_reassign_user_owned_data.sql`) le rende
  illeggibili. Va fatto in Python, decifrando e ricifrando.
- La lunghezza approssimativa dei valori resta visibile.
