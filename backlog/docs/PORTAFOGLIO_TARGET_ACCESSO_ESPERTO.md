# Piano - Accesso Esperto al Portafoglio Target

## Obiettivo

Introdurre la possibilita' per un utente proprietario del portafoglio di:

- concedere accesso ad un **esperto**
- limitare l'accesso al solo **portafoglio target** (non alle transazioni reali)
- permettere all'esperto di:
  - modificare i target esistenti
  - inserire nuovi titoli
  - assegnare/modificare i **pesi**

Focus: collaborazione controllata, tracciabile e sicura.

## Caso d'uso principale

- Utente retail crea il proprio portafoglio
- Definisce (o vuole definire) un portafoglio target
- Invita un consulente/esperto
- L'esperto aggiorna la lista titoli e i pesi target
- L'utente vede le modifiche e puo' accettarle/usarle come riferimento

## Ambito (Scope)

### In scope

- Condivisione del **portafoglio target** con ruolo `expert_editor`
- CRUD target allocations da parte dell'esperto
- Inserimento di nuovi titoli nel target (se non presenti nel target)
- Validazioni sui pesi (somma, duplicati, valori negativi)
- Audit log delle modifiche (chi, quando, cosa)
- Revoca accesso da parte del proprietario

### Out of scope (prima fase)

- Accesso alle transazioni reali del portafoglio
- Operativita' di trading / invio ordini
- Workflow legale/compliance da consulente abilitato
- Commenti/chat in-app
- Versioning avanzato con approvazione multi-step

## Modello autorizzativo (consigliato)

Ruoli per il perimetro "target portfolio":

- `owner`: proprietario del portafoglio, pieno controllo
- `expert_editor`: puo' leggere e modificare solo il target
- `viewer` (opzionale fase successiva): sola lettura del target

Regole chiave:

- L'esperto **non** puo' vedere/modificare transazioni, cash, performance reali (salvo estensioni future)
- L'accesso e' assegnato a livello di portfolio specifico
- Il proprietario puo' revocare accesso in ogni momento

## Proposta di Data Model (MVP)

Riutilizzare l'evoluzione prevista in `docs/MULTI_UTENTE.md` (`portfolio_access`) con scope esplicito.

### Tabella nuova (consigliata): `portfolio_access`

Campi minimi:

- `id`
- `portfolio_id`
- `granted_to_user_id`
- `granted_by_user_id`
- `role` (`owner`, `expert_editor`, `viewer`)
- `scope` (`target_only`, futuro: `full_portfolio`)
- `status` (`pending`, `active`, `revoked`)
- `created_at`
- `updated_at`
- `revoked_at` (nullable)

Vincoli consigliati:

- unique attiva su `(portfolio_id, granted_to_user_id, scope)` per evitare duplicati
- check su `role` e `scope`

### Audit log (consigliato)

Nuova tabella: `portfolio_target_change_log`

Campi minimi:

- `id`
- `portfolio_id`
- `actor_user_id`
- `action` (`add_asset`, `update_weight`, `remove_asset`, `rebalance`)
- `payload_json` (prima/dopo sintetico)
- `created_at`

## Impatto su entita' esistenti

### `portfolio_target_allocations`

Nessun cambio strutturale obbligatorio per iniziare, ma serve enforcement lato backend:

- `owner` puo' CRUD
- `expert_editor` puo' CRUD se accesso `active` e `scope = target_only`
- altri utenti: `404`

Opzionale (utile per audit rapidi):

- `updated_by_user_id`

## Flusso funzionale (MVP)

## 1. Concessione accesso

- Owner apre schermata "Condivisione target"
- Seleziona utente esperto (email o user id)
- Assegna ruolo `expert_editor`
- Sistema crea record `portfolio_access` in `pending` o `active`

Nota:

- Se non esiste ancora una rubrica utenti ricercabile, MVP pragmatico con inserimento email + match account esistente.

## 2. Lavoro dell'esperto

- Esperto vede i portfolio condivisi con badge "Target only"
- Apre il target allocation editor
- Puo':
  - aggiungere un titolo
  - modificare il peso di un titolo
  - rimuovere un titolo
  - salvare ribilanciamento

Validazioni:

- peso `>= 0`
- nessun ticker duplicato nel target
- somma pesi = `100%` (o tolleranza configurabile, es. `99.99-100.01`)

## 3. Visibilita' per il proprietario

- Owner vede ultimo aggiornamento (utente/data)
- Owner visualizza target corrente aggiornato
- (Opzionale fase 2) diff tra versione precedente e nuova

## 4. Revoca accesso

- Owner revoca
- `portfolio_access.status = revoked`
- Esperto perde accesso immediatamente alle API target

## API / Backend - Piano di implementazione

## Fase 1 - Access control backend (minimo)

- Introdurre funzione centralizzata tipo:
  - `can_read_target(portfolio_id, user_id)`
  - `can_edit_target(portfolio_id, user_id)`
- Supportare `owner` + `expert_editor(target_only)`
- Enforce su tutte le route target allocation CRUD

Regola sicurezza:

- Se portfolio non accessibile -> `404`

## Fase 2 - Endpoint gestione accessi

Endpoint suggeriti:

- `POST /portfolios/{id}/target-access/invite`
- `GET /portfolios/{id}/target-access`
- `PATCH /portfolios/{id}/target-access/{access_id}` (attiva/revoca/cambio ruolo)
- `DELETE /portfolios/{id}/target-access/{access_id}` (opzionale alias revoca)

## Fase 3 - Audit log

- Loggare ogni modifica target fatta da owner o esperto
- Esporre endpoint lettura audit (owner only)

## Frontend - Piano di implementazione

## UI minima (MVP)

Nuove aree:

- sezione in portfolio: `Condivisione target`
- lista accessi (utente, ruolo, stato, data ultimo update)
- azione `Invita esperto`
- azione `Revoca`

Nel target editor:

- indicatore permessi (`Owner`, `Esperto - target only`)
- warning chiaro: "Modifichi il portafoglio target, non il portafoglio reale"

## UX consigliata

- Distinguere visivamente:
  - portafoglio reale
  - portafoglio target
- Evitare ambiguita' su impatto delle modifiche

## Sicurezza e rischi

Rischi principali:

- Bug di autorizzazione che espone dati reali a `expert_editor`
- Endpoint target che accettano `portfolio_id` senza verifica accesso
- UI che mostra KPI reali in schermata condivisa

Mitigazioni:

- Enforce backend centralizzato
- Test automatici owner/expert/utente esterno
- `404` su risorse non accessibili
- Audit log per tracciabilita'

## Test minimi (accettazione)

- Owner puo' invitare esperto su portfolio A
- Esperto vede e modifica target di A
- Esperto non vede transazioni di A
- Esperto non modifica target di portfolio non condiviso
- Revoca accesso blocca subito CRUD target
- Audit log registra `actor_user_id` corretto
- Somma pesi non valida -> errore validazione

## Rollout incrementale (consigliato)

1. Backend authz target-only + test
2. Tabella `portfolio_access` + CRUD accessi
3. UI condivisione target (invite/revoke)
4. Audit log
5. Migliorie UX (diff versioni, notifiche)

## Open questions (da chiudere prima dello sviluppo)

1. L'esperto deve essere un utente gia' registrato o puo' essere invitato via email?
2. Le modifiche dell'esperto devono essere immediate o soggette ad approvazione owner?
3. La somma pesi deve essere obbligatoriamente `100%` o e' ammesso cash residuo?
4. Serve limitare il numero massimo di esperti per portfolio in MVP?

## Esito atteso MVP

Il proprietario puo' delegare ad un esperto la costruzione/manutenzione del **portafoglio target** in modo sicuro, senza concedere accesso ai dati operativi reali del portafoglio.

## Checklist tecnica (implementazione)

### Database / Migrazioni

- [ ] Creare tabella `portfolio_access`
- [ ] Definire enum/check per `role` (`owner`, `expert_editor`, `viewer`)
- [ ] Definire enum/check per `scope` (`target_only`)
- [ ] Definire enum/check per `status` (`pending`, `active`, `revoked`)
- [ ] Aggiungere indice su `portfolio_id`
- [ ] Aggiungere indice su `granted_to_user_id`
- [ ] Aggiungere unique constraint su `(portfolio_id, granted_to_user_id, scope)` (valutare solo record attivi)
- [ ] Creare tabella `portfolio_target_change_log`
- [ ] Aggiungere indici audit (`portfolio_id`, `created_at`)
- [ ] (Opzionale) aggiungere `updated_by_user_id` a `portfolio_target_allocations`

### Backend - Autorizzazione

- [ ] Introdurre helper centralizzato `can_read_target(portfolio_id, user_id)`
- [ ] Introdurre helper centralizzato `can_edit_target(portfolio_id, user_id)`
- [ ] Supportare caso `owner` (proprietario portfolio)
- [ ] Supportare caso `expert_editor` con `scope = target_only` e `status = active`
- [ ] Restituire `404` per portfolio non accessibile
- [ ] Verificare che le route target non espongano dati portfolio reali

### Backend - API accessi

- [ ] Implementare `POST /portfolios/{id}/target-access/invite`
- [ ] Implementare `GET /portfolios/{id}/target-access`
- [ ] Implementare `PATCH /portfolios/{id}/target-access/{access_id}` (attiva/revoca)
- [ ] Validare che solo `owner` possa invitare/revocare
- [ ] Gestire errore invito duplicato su stesso portfolio/scope
- [ ] Gestire ricerca utente destinatario (email o `user_id`, secondo scelta MVP)

### Backend - Target allocations

- [ ] Applicare authz a tutte le route CRUD di `portfolio_target_allocations`
- [ ] Consentire all'esperto inserimento nuovi titoli nel target
- [ ] Validare peso `>= 0`
- [ ] Bloccare ticker duplicati nel target
- [ ] Validare somma pesi (`100%` o regola definita)
- [ ] Aggiornare timestamp/metadata ultimo update

### Backend - Audit log

- [ ] Loggare `add_asset`
- [ ] Loggare `update_weight`
- [ ] Loggare `remove_asset`
- [ ] Loggare `rebalance` (se update massivo)
- [ ] Salvare `actor_user_id` corretto (owner vs esperto)
- [ ] Esporre endpoint lettura audit per owner (opzionale MVP+, consigliato)

### Frontend - UI condivisione target

- [ ] Aggiungere sezione `Condivisione target` nella pagina portfolio
- [ ] Visualizzare lista accessi (utente, ruolo, stato)
- [ ] Aggiungere azione `Invita esperto`
- [ ] Aggiungere azione `Revoca`
- [ ] Mostrare stato `pending/active/revoked`
- [ ] Gestire errori API (utente non trovato, duplicato, permessi)

### Frontend - Target editor

- [ ] Mostrare badge ruolo (`Owner` / `Esperto - target only`)
- [ ] Mostrare warning "stai modificando il portafoglio target"
- [ ] Abilitare/disabilitare controlli in base ai permessi reali ricevuti dal backend
- [ ] Aggiornare UI dopo salvataggio con ultimo autore/data modifica
- [ ] (Opzionale) mostrare storico modifiche / diff

### Test automatici

- [ ] Test unit/helper authz: owner puo' leggere/modificare target
- [ ] Test unit/helper authz: expert_editor attivo puo' modificare target
- [ ] Test unit/helper authz: expert_editor revocato non puo' accedere
- [ ] Test API: utente esterno riceve `404`
- [ ] Test API: esperto non accede a transazioni/summary reali
- [ ] Test API: validazione somma pesi fallisce correttamente
- [ ] Test API: revoca accesso blocca CRUD immediatamente
- [ ] Test audit: `actor_user_id` e `action` corretti

### Test manuali (smoke)

- [ ] Owner invita esperto su un portfolio
- [ ] Esperto apre portfolio condiviso e modifica pesi
- [ ] Owner vede target aggiornato
- [ ] Esperto prova ad aprire dati reali portfolio -> negato
- [ ] Owner revoca accesso -> esperto non salva piu'

### Rollout / Operativita'

- [ ] Abilitare feature flag (se disponibile) per `target_expert_access`
- [ ] Deploy backend con authz prima della UI
- [ ] Deploy UI di condivisione target
- [ ] Eseguire smoke test con 2 utenti reali (owner + esperto)
- [ ] Monitorare errori authz e regressioni sulle route target

## Piano per Sprint (sequenziale) + Stima effort

Stime indicative per 1 sviluppatore full-stack, escluse attese esterne/compliance.

### Sprint 1 - Fondazioni sicurezza (Backend + DB)

Obiettivo:

- mettere in sicurezza il perimetro "target only" lato backend
- preparare il modello dati accessi

Task principali:

- migrazione `portfolio_access`
- helper authz `can_read_target` / `can_edit_target`
- enforcement authz su CRUD target allocations
- validazioni pesi/ticker duplicate
- test automatici authz/API core

Deliverable:

- esperto non ancora invitabile via UI, ma backend pronto e sicuro
- route target protette con regole `owner` / `expert_editor`

Stima effort:

- DB/migrazioni: `0.5 - 1` giorno
- backend authz + refactor route target: `1 - 2` giorni
- test automatici core: `0.5 - 1` giorno
- Totale Sprint 1: `2 - 4` giorni

### Sprint 2 - Gestione accessi (API + UI minima)

Obiettivo:

- permettere all'owner di invitare/revocare un esperto
- rendere visibile la condivisione target in UI

Task principali:

- endpoint `invite/list/patch(revoke)`
- gestione destinatario (email o `user_id`, scelta MVP)
- sezione UI `Condivisione target`
- lista accessi + stato
- azioni `Invita esperto` / `Revoca`
- gestione errori UX base

Deliverable:

- owner puo' abilitare/disabilitare accesso esperto al target
- esperto vede/modifica target se accesso `active`

Stima effort:

- backend API accessi: `1 - 2` giorni
- frontend UI condivisione target: `1 - 2` giorni
- integrazione + smoke test: `0.5 - 1` giorno
- Totale Sprint 2: `2.5 - 5` giorni

### Sprint 3 - Audit, rifiniture e rollout controllato

Obiettivo:

- migliorare tracciabilita' e affidabilita' del flusso
- preparare rilascio con monitoraggio

Task principali:

- tabella `portfolio_target_change_log`
- logging modifiche target (owner/esperto)
- (Opzionale) endpoint audit per owner
- indicatori UI ultimo autore/data modifica
- feature flag + rollout progressivo
- smoke test end-to-end con 2 utenti

Deliverable:

- modifiche target tracciate
- rollout monitorabile con rischio ridotto

Stima effort:

- audit log backend: `1 - 1.5` giorni
- UI miglioramenti minimi: `0.5 - 1` giorno
- rollout/smoke/regressioni: `0.5 - 1` giorno
- Totale Sprint 3: `2 - 3.5` giorni

## Stima complessiva (range)

- MVP tecnico senza audit UI avanzata: `4.5 - 9` giorni
- MVP con audit log e rollout curato: `6.5 - 12.5` giorni

## Dipendenze / Decisioni che impattano la stima

- scelta invito via `email` vs solo `user_id`
- presenza di componenti UI/Design System gia' pronti
- copertura test backend esistente sulle route target
- disponibilita' feature flag e osservabilita' (log/error tracking)

## Priorita' MoSCoW

### Must Have (MVP indispensabile)

- Modello accessi `portfolio_access` con ruolo `expert_editor` e scope `target_only`
- Enforcement backend centralizzato su tutte le route target allocations
- Owner puo' invitare e revocare accesso esperto
- Esperto puo' aggiungere titoli e modificare pesi del portafoglio target
- Validazioni target (pesi non negativi, no duplicati, somma pesi secondo regola definita)
- Esperto non puo' accedere a transazioni/dati reali del portafoglio
- Test automatici minimi su authz e regressioni principali

### Should Have (fortemente consigliato nel primo rilascio)

- Audit log modifiche target (`actor_user_id`, `action`, timestamp)
- UI con sezione `Condivisione target` dedicata
- Indicatore chiaro in UI "Target only" / warning su impatto modifiche
- Gestione stato accesso (`pending`, `active`, `revoked`)
- Smoke test end-to-end con due utenti reali

### Could Have (migliorie non bloccanti)

- Diff tra versione precedente e nuova del target
- Endpoint/UI storico modifiche leggibile dal proprietario
- Supporto ruolo `viewer` per sola lettura target
- Notifiche all'owner dopo modifica dell'esperto
- Limite configurabile numero esperti per portfolio

### Won't Have (questa fase)

- Accesso esperto al portafoglio reale / transazioni / performance operative
- Invio ordini o operativita' broker
- Workflow approvazione multi-step formale
- Chat/commenti in-app
- Compliance consulenziale / contrattualistica integrata
