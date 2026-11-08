---
id: TASK-57
title: "Cifratura a livello di campo dei dati personali nel database"
status: "In Progress"
priority: "high"
created: 2026-11-08
labels: ["backend", "security", "database", "gdpr"]
---

# Cifratura a livello di campo dei dati personali

## Contesto

Il database (Postgres su Supabase) è già cifrato su disco da Supabase, ma chi ottiene la
`DATABASE_URL`, un dump o l'accesso alla dashboard legge tutto in chiaro. Cifrare *tutte*
le colonne romperebbe le aggregazioni SQL (posizioni, riepiloghi, PAC) e non avrebbe senso
per i dati di mercato pubblici. Si cifrano quindi lato applicazione solo i campi testuali
personali, lasciando in chiaro importi, quantità, date e ID.

## Design

- AES-256-GCM (`cryptography`), envelope encryption:
  - KEK (chiave master) da variabile d'ambiente `DATA_ENCRYPTION_KEYS` (keyring versionato
    `kid:base64key,...`, la prima è quella attiva) per permettere la rotazione.
  - DEK casuale per utente, salvata cifrata con la KEK in `user_data_keys`.
    Cancellare la riga rende illeggibili i dati di quell'utente (crypto-shredding / GDPR).
- AAD = `tabella:colonna:owner_user_id`: un valore copiato su altra riga/utente non si decifra.
- Valori cifrati salvati come testo con prefisso versionato; i valori legacy in chiaro
  restano leggibili (migrazione progressiva + script di backfill).
- Blind index HMAC-SHA256 per i campi cercati per uguaglianza (email).
- In `APP_ENV=prod` l'avvio fallisce se la chiave manca; in dev/test i dati restano in chiaro.

## Colonne

| Tabella | Colonna | Note |
|---|---|---|
| `app_users` | `email` | + `email_bidx` per le ricerche |
| `portfolios` | `name` | |
| `transactions` | `notes` | |
| `csv_import_batches` | `original_filename`, `preview_data` | `source_sha256` spostato in colonna dedicata |
| `doctor_policy_sets` | `name` | |

Restano in chiaro: importi, quantità, prezzi, date, ID, dati di mercato.

## Acceptance Criteria

- [ ] #1 Modulo `app/crypto` con cifratura/decifratura AES-256-GCM, keyring con rotazione, DEK per utente, blind index
- [ ] #2 Le colonne elencate sono scritte cifrate e lette in chiaro dalle API, senza cambiare i contratti
- [ ] #3 I valori legacy in chiaro sono ancora leggibili; uno script di backfill li cifra (idempotente, con `--dry-run`)
- [ ] #4 Migrazione SQL in `database/migrations` e `schema.sql` aggiornato
- [ ] #5 In prod l'avvio fallisce senza `DATA_ENCRYPTION_KEYS`; `render.yaml` e documentazione aggiornati
- [ ] #6 Test unitari: round-trip, AAD errata, rotazione chiavi, valori legacy, crypto-shredding
- [ ] #7 La suite di test esistente passa
