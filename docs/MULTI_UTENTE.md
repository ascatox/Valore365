# Piano Multi Utente (MVP -> Evoluzione)

## Obiettivo

Rendere il sistema **multi utente** con:

- isolamento dati per utente
- compatibilita' con auth esistente (`AuthContext`)
- migrazione graduale senza rompere il funzionamento attuale

Approccio consigliato: **tenant = utente** (MVP), con possibilita' futura di supportare team/org.

## Stato Attuale (sintesi)

- Il backend ha gia' `AuthContext` e `require_auth`
- In ambiente dev, il backend usa `dev-user` quando Clerk e' disabilitato
- Le tabelle applicative principali non sono ancora scoping per utente
- Quindi oggi il sistema e' autenticato ma non realmente multi-tenant

## Strategia Consigliata

Partire con un modello semplice:

- dati di portafoglio **posseduti da un utente**
- `assets` e dati di mercato **globali** (condivisi)

Questo riduce complessita' e duplicazione dati (asset/prezzi/FX).

## Fasi di Implementazione

## Fase 0 - Decisioni di base

Definire e congelare:

- modello tenancy: `user-owned` (consigliato)
- comportamento in dev: utente fittizio `dev-user`
- risorse globali vs per utente

Scelta consigliata:

- Globali: `assets`, `asset_provider_symbols`, `price_bars_*`, `fx_rates_*`
- Per utente: `portfolios`, `transactions`, `portfolio_target_allocations`, `api_idempotency_keys`

## Fase 1 - Data Model Multi Utente (MVP)

Aggiungere `owner_user_id` alle tabelle utente-specifiche.

Tabelle da aggiornare:

- `portfolios` (obbligatorio)
- `transactions` (consigliato, anche se derivabile dal portfolio)
- `portfolio_target_allocations` (separata e user-scoped)
- `api_idempotency_keys` (consigliato, per evitare collisioni cross-user)

Gia' allineata:

- `app_user_settings` usa `user_id`

Non aggiungere (per ora) `owner_user_id` a:

- `assets`
- `asset_provider_symbols`
- `price_bars_1d`, `price_bars_1m`, `price_ticks`
- `fx_rates_1d`

## Fase 2 - Migrazioni DB

Ordine sicuro consigliato:

1. aggiungere colonne `owner_user_id` come nullable
2. backfill dati esistenti a `dev-user`
3. aggiungere indici
4. rendere `owner_user_id` `NOT NULL`

Indici consigliati:

- `idx_portfolios_owner_user_id`
- `idx_transactions_owner_user_id`
- indici composti in base alle query principali (es. `(owner_user_id, portfolio_id, trade_at)`)

Nota:

- dove possibile, usare anche vincoli/foreign key coerenti con il modello

## Fase 3 - Repository Scoping (backend)

Refactor dei metodi repository per richiedere `user_id` sulle operazioni user-scoped.

Esempi:

- `list_portfolios(user_id)`
- `create_portfolio(payload, user_id)`
- `get_summary(portfolio_id, user_id)`
- `get_positions(portfolio_id, user_id)`
- `list_transactions(portfolio_id, user_id)`
- `create/update/delete transaction` con verifica ownership
- target allocation CRUD con verifica ownership

Regola di sicurezza:

- risorsa non posseduta -> rispondere `404` (non `403`) per non esporre l'esistenza di risorse altrui

## Fase 4 - API Layer (`main.py`)

Aggiornare gli endpoint per passare `_auth.user_id` ai metodi repository.

Linee guida:

- tutte le route portfolio/transactions/target/analytics devono essere user-scoped
- evitare endpoint "admin" non realmente amministrativi
- mantenere compatibilita' dev con `dev-user`

## Fase 5 - Frontend

Impatto minimo se il backend e' correttamente filtrato per utente:

- la maggior parte delle pagine continuera' a funzionare senza grossi cambi
- `Settings` e' gia' concettualmente user-scoped
- eventuali miglioramenti futuri: profilo utente, switch account, indicatori tenancy

## Fase 6 - Test e Verifiche

Test minimi necessari:

- utente A non vede portfolio di utente B
- utente A non puo' leggere/modificare/eliminare transazioni di B
- target allocation isolata per utente
- analytics/dashboard non aggregano dati di altri utenti
- `api_idempotency_keys` isolate per utente
- `app_user_settings` isolate per utente
- migrazione legacy -> `dev-user` corretta

Test smoke consigliati:

- creare portfolio con utente A
- login utente B -> nessun portfolio visibile
- creare stessa chiave idempotenza su due utenti -> nessun conflitto

## Fase 7 - Evoluzione (Team / Organizzazioni) [Opzionale]

Quando serve collaborazione:

- `organizations`
- `organization_members`
- `portfolio_access` con ruoli (`owner`, `editor`, `viewer`)

Possibile evoluzione:

- `portfolios.owner_user_id`
- `portfolios.organization_id` (uno dei due valorizzato)

Non consigliato introdurre subito questa complessita' nel MVP.

## Scelte Architetturali Consigliate (Riepilogo)

- `assets` e prezzi globali
- dati portfolio e transazioni user-scoped
- enforcement della sicurezza lato backend (non frontend)
- `404` per risorse non possedute
- migrazione incrementale e reversibile

## Rischi Principali

- query non filtrate per `user_id` -> data leak
- endpoint batch/analytics che usano metodi repository legacy senza scoping
- migrazione DB incompleta (backfill mancante prima di `NOT NULL`)
- caching/idempotenza non isolata per utente

## Checklist Operativa (Prossimo Step)

1. Mappare tabelle user-scoped vs globali
2. Scrivere migrazioni `owner_user_id` + backfill `dev-user`
3. Refactor repository/API per `user_id` (partire da portfolios + transactions)
4. Aggiungere test di isolamento dati
5. Verifica end-to-end con due utenti

## Note di Implementazione Pragmatica

- Fare il rollout per blocchi verticali:
  - prima `portfolios`
  - poi `transactions`
  - poi `target allocations`
  - poi analytics/dashboard
- Evitare refactor "big bang"
- Ogni fase deve lasciare il sistema deployabile
