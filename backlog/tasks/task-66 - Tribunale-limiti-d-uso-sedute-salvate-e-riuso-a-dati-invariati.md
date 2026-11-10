---
id: TASK-66
title: 'Tribunale: limiti d''uso, sedute salvate e riuso a dati invariati'
status: To Do
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - doctor
  - tribunale
  - backend
  - database
milestone: m-0
dependencies:
  - TASK-65
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Una seduta costa sette chiamate al modello. Senza limiti, pochi utenti possono consumare la chiave del server; senza memoria, riaprire la pagina significa pagare di nuovo per lo stesso identico portafoglio. Serve salvare l'ultima seduta per scope, riproporla finché i dati non cambiano e mettere un tetto giornaliero a chi usa la chiave del server.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Una seduta conclusa viene salvata per utente e scope insieme all'hash del fascicolo; i contenuti sono cifrati a livello di campo come gli altri dati personali
- [ ] #2 L'endpoint dell'ultima seduta la restituisce con la data e indica se il fascicolo attuale è ancora lo stesso o se i dati sono cambiati
- [ ] #3 Avviare una seduta con fascicolo invariato restituisce quella salvata senza chiamare il modello, salvo richiesta esplicita di rifarla
- [ ] #4 Chi usa la chiave del server ha un limite giornaliero di sedute configurabile; al superamento riceve un errore dedicato con l'ora di ripristino. Chi usa la propria chiave non ha questo limite
- [ ] #5 Una seduta interrotta o fallita non viene salvata e non consuma il limite
- [ ] #6 Eliminare un portafoglio o l'account elimina le sedute collegate
- [ ] #7 La migrazione è inclusa in `database/migrations/` e in `database/schema.sql`; i test coprono salvataggio, riuso, dati cambiati, limite e cancellazione
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/services/tribunal/store.py`, `database/migrations/<data>_tribunal_sessions.sql`, le modifiche a `database/schema.sql` e `database/supabase_full_setup.sql`, i relativi test. Modifiche minime e localizzate a `orchestrator.py` e `routes_tribunal.py` di TASK-65.
Riferimenti: `docs/field-encryption.md` e `app/crypto/`; `services/doctor_policy/store.py` per lo stile del repository; `rate_limit.py`.
Aggiornamento da TASK-60: il backend non ha un flusso di cancellazione dell'account; esporre `TribunalStore.delete_for_user` e la cascata sulla cancellazione del portafoglio, e segnalare l'AC #6 come parziale per la parte account. `supabase_full_setup.sql` non è più mantenuto come schema completo: aggiornarlo solo se coerente con `docs/doctor2/api-contracts.md`.
<!-- SECTION:NOTES:END -->
