# Piano Incrementale: Evoluzione in SaaS + Mini Marketplace

## Obiettivo

Evolvere Valore365 da portfolio tracker personale a:

- SaaS multiutente monetizzabile
- con un piccolo marketplace iniziale (template/allocazioni/strategie, non execution)
- mantenendo rollout incrementale e basso rischio

Focus pragmatico:

- prima migliorare affidabilita', billing e tenancy
- poi introdurre marketplace "light" di contenuti/portfolio target
- evitare subito complessita' da broker integration / order execution

## Stato Attuale (base di partenza)

Valore365 oggi ha gia':

- auth (Clerk) e backend FastAPI
- multiutente in corso/avanzato (owner_user_id su tabelle user-scoped)
- portfolio, transazioni, target allocation, analytics
- pricing/backfill storico
- frontend React/Mantine

Questo e' un buon punto di partenza per un SaaS "research + tracking".

## Visione SaaS (versione realistica)

### Prodotto

Valore365 come "Portfolio OS personale":

- tracking e analisi
- target allocation
- confronto target vs reale
- strumenti di pianificazione/ribilanciamento
- contenuti acquistabili/attivabili dal marketplace (template, modelli, bundle)

### Marketplace (MVP)

Un piccolo marketplace interno di elementi digitali:

- template di allocazione target (ETF, lazy portfolios, settoriali, dividend, ecc.)
- bundle di watchlist/asset set
- preset di regole (es. limiti peso, soglie rebalance)
- eventuali "strategie modello" informative (non consulenza personalizzata)

No execution:

- nessun invio ordini
- nessuna custodia
- nessun consiglio personalizzato automatico

## Principi guida

1. Vertical slices deployabili
- ogni fase deve lasciare il sistema usabile e monetizzabile meglio di prima

2. Compliance-first messaging
- prodotto di tracking/analisi, non broker
- marketplace di contenuti/preset, non segnali personalizzati "chiavi in mano"

3. Minima complessita' operativa
- no microservizi iniziali
- no motore marketplace "generico" finche' non serve

4. Misurare prima di scalare
- introdurre analytics prodotto e conversion funnel presto

## Roadmap Incrementale (consigliata)

## Fase 1 - SaaS Foundation (stabilizzazione)

### Obiettivo

Chiudere il minimo necessario per operare come SaaS affidabile.

### Deliverable

- completamento multiutente (backend + migrazioni + test isolamento)
- gestione errori/observability minima
- configurazione ambiente prod robusta
- hardening auth + CORS + rate limiting base
- backup/restore DB documentato

### Upgrade tecnici

- test automatici su isolamento utente (A non vede B)
- audit log tecnico minimo (errori backend, job pricing, refresh)
- health checks piu' granulari (DB, provider)
- idempotency per-user completata (gia' in corso)

### KPI di uscita fase

- zero data leak cross-user nei test
- deploy ripetibile
- smoke test REST verde in CI

## Fase 2 - Piani SaaS e Billing (monetizzazione base)

### Obiettivo

Monetizzare il core prodotto prima del marketplace.

### Piani suggeriti

- Free:
  - 1 portfolio
  - storico/analytics limitati
  - refresh meno frequente
- Pro:
  - piu' portfolio
  - analytics completi
  - target/rebalance avanzati
  - export
- Creator (fase successiva, solo se marketplace):
  - pubblicazione template
  - revenue share

### Deliverable

- entitlements lato backend (feature flags per piano)
- billing provider (Stripe consigliato)
- webhook billing -> aggiornamento piano utente
- UI account/billing semplice

### Modello dati minimo

Nuove tabelle:

- `subscriptions`
- `billing_events` (audit webhooks)
- eventuale `feature_entitlements` (o calcolate)

### Nota architetturale

Le feature devono essere enforce lato backend, non solo frontend.

## Fase 3 - Marketplace MVP (template target allocation)

### Obiettivo

Lanciare un piccolo marketplace con il minimo per validare domanda.

### Cosa vendere (MVP)

- Template allocazione target (JSON + metadata)
- Categorie (es. ETF, Income, Growth, Difensivo)
- Versioni/template updates

### Cosa puo' fare l'utente

- sfogliare catalogo
- vedere dettaglio template
- acquistare (o riscattare free)
- applicare al portfolio come target allocation
- clonare template in un portfolio (senza transazioni)

### Cosa puo' fare il creator/admin (inizialmente interno)

- creare/aggiornare template
- pubblicare/non pubblicare
- taggare e categorizzare

### Modello dati suggerito (MVP)

- `marketplace_products`
  - id, slug, title, description, status, price, currency, type
- `marketplace_product_versions`
  - product_id, version, payload_json, changelog, published_at
- `marketplace_purchases`
  - user_id, product_id, purchased_at, price_paid
- `marketplace_entitlements`
  - user_id, product_id, source (purchase/free/admin)

Payload template (JSON) esempio:

- nome template
- lista asset + peso target
- note/rationale
- profilo rischio (label)
- disclaimer

### API MVP

- `GET /api/marketplace/products`
- `GET /api/marketplace/products/{slug}`
- `POST /api/marketplace/products/{id}/purchase`
- `POST /api/marketplace/products/{id}/apply-to-portfolio`

### UI MVP

- pagina Catalogo
- pagina Dettaglio prodotto
- bottone "Applica al portfolio" (se entitlement presente)

## Fase 4 - Workflow di Applicazione e Rebalance assistito

### Obiettivo

Aumentare il valore del marketplace collegandolo ai workflow esistenti.

### Deliverable

- applicazione template -> target allocation del portfolio
- diff chiaro tra target attuale e template
- anteprima rebalance dal template (gia' avete una base)
- versioning + "aggiorna al template v2" con conferma

### UX chiave

- "Applica come nuovo target" vs "Merge con target esistente"
- preview impatto prima del salvataggio
- storico applicazioni template

## Fase 5 - Marketplace Creator (piccolo, controllato)

### Obiettivo

Aprire la pubblicazione a un piccolo numero di creator verificati.

### Approccio consigliato

- curated marketplace (approvazione manuale)
- pochi creator all'inizio
- contenuti standardizzati

### Deliverable

- ruolo creator
- backoffice creator (draft/publish)
- moderation queue/admin review
- revenue share reporting semplice

### Rischi da gestire

- contenuti fuorvianti / claim eccessivi
- compliance / promesse di rendimento
- qualita' scarsa del catalogo

## Fase 6 - Growth e difendibilita'

### Possibili estensioni (dopo validazione)

- bundle di template
- aggiornamenti premium / "research packs"
- benchmark custom
- alerting (drift target, variazioni peso)
- report PDF shareable
- import transazioni automatizzato (CSV broker)

## Architettura proposta (incrementale, senza strappi)

## Backend

Mantieni il monolite FastAPI, aggiungendo moduli:

- `marketplace_repository.py` (o sezioni in repository esistente all'inizio)
- `billing_service.py`
- `entitlements_service.py`

Consiglio pratico:

- inizialmente usare lo stesso DB Postgres
- separare logicamente con tabelle + namespace funzionale
- estrarre servizi solo se compaiono colli di bottiglia reali

## Frontend

Aggiunte incrementali:

- route `/marketplace`
- route `/marketplace/:slug`
- sezione Account/Billing in `Settings`
- badge piano (`Free/Pro`)

## Dati & Multiutente

Continuare con il modello attuale:

- `assets` e prezzi globali
- dati portfolio user-scoped
- marketplace:
  - catalogo globale
  - acquisti/entitlements user-scoped

## Sicurezza, Compliance e Trust (obbligatorio)

### Sicurezza minima

- rate limiting su endpoint sensibili (auth-adjacent, purchase, apply)
- audit trail per acquisti/applicazioni template
- validazione server-side del payload template

### Compliance / messaging

Testi chiari in UI e T&C:

- non e' consulenza finanziaria personalizzata
- contenuti informativi/educativi
- nessuna garanzia di rendimento

### Marketplace moderation

- checklist contenuti ammessi
- blocco claim ingannevoli
- versioning + rollback template

## Metriche da tracciare (prima del marketplace pubblico)

### SaaS core

- activation: utente crea portfolio + prima transazione + target allocation
- retention D7 / D30
- conversion free -> pro
- portfolio attivi per utente

### Marketplace

- view prodotto -> acquisto
- acquisto -> applicazione al portfolio
- applicazioni per prodotto
- refund/chargeback (se presenti)

## Sequenza raccomandata (90 giorni)

### Sprint 1-2

- chiusura multiutente + test
- bugfix/stabilita' dashboard/portfolio
- logging/monitoring base

### Sprint 3-4

- billing + piani SaaS
- entitlements backend
- UI account/piano

### Sprint 5-6

- marketplace MVP (catalogo + detail + acquisto simulato/real billing)
- apply template -> target allocation

### Sprint 7-8

- miglioramenti UX rebalance/apply
- analytics prodotto e funnel
- hardening compliance e moderation admin

## Rischi principali e mitigazioni

### 1. Scope creep marketplace

Rischio:
- voler supportare "segnali", "social", "copy trading" troppo presto

Mitigazione:
- partire solo da template target allocation statici/versionati

### 2. Complessita' billing/entitlements

Rischio:
- incoerenza tra stato Stripe e accesso feature

Mitigazione:
- source of truth: webhook + tabella `subscriptions`
- fallback manuale admin

### 3. Compliance/posizionamento ambiguo

Rischio:
- percezione di advice personalizzato

Mitigazione:
- UX, copy e ToS chiari
- no promesse, no execution, no suitability engine iniziale

## Backlog tecnico (ordine consigliato)

1. Completare e testare Multi Utente end-to-end
2. Aggiungere entitlements backend per piano
3. Integrare Stripe + webhook robusti
4. Introdurre tabelle marketplace MVP
5. API catalogo + apply template
6. UI catalogo e dettaglio prodotto
7. Tracking metriche funnel
8. Backoffice admin per publishing template

## Raccomandazione finale

La strada piu' efficace e':

- **prima SaaS Pro solido**
- **poi marketplace curato di template target**

Questo sfrutta molto bene il core gia' costruito (target allocation + analytics + rebalance preview) senza entrare subito in complessita' regolatoria e operativa da fintech execution.
