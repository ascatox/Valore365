---
id: TASK-71
title: 'Tribunale: prove avversarie, E2E e documentazione'
status: Done
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - doctor
  - tribunale
  - test
  - docs
milestone: m-0
dependencies:
  - TASK-66
  - TASK-69
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La promessa del Tribunale è che nessun numero inventato e nessun consiglio d'acquisto raggiunga l'utente. Va dimostrata con prove costruite per rompere il sistema, non solo con i test felici dei singoli moduli. Questo task chiude il lavoro: prove avversarie dall'endpoint allo schermo, E2E su stack reale con LLM finto, e documentazione per utente e sviluppatore.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un LLM finto produce a comando: numeri scritti nel testo, fatti inesistenti, indicazioni di acquisto, strumenti fuori dal portafoglio, JSON non valido, risposta lenta; per ciascun caso un test dimostra che nulla di scorretto compare negli eventi inviati al frontend
- [x] #2 Un portafoglio di prova con un'istruzione nascosta nel nome di uno strumento non altera il comportamento delle voci
- [x] #3 Un test verifica su una seduta completa che ogni numero visibile all'utente coincide con un valore del fascicolo
- [x] #4 Un E2E su stack reale copre: avvio della seduta dal Doctor, comparsa progressiva delle tre voci, apertura di un fatto citato, sintesi, riapertura con seduta salvata, vista aggregata, mobile
- [x] #5 Uno script opzionale esegue una seduta contro un provider reale sui portafogli di esempio e riporta argomenti ammessi e scartati per voce e per codice, per valutare modifiche a prompt e modello
- [x] #6 README e CHANGELOG descrivono il Tribunale e la variabile `DOCTOR_TRIBUNAL_ENABLED`; `docs/tribunale/test-report.md` riporta cosa è stato eseguito e l'esito
- [x] #7 La suite backend e frontend esistente passa per intero
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `scripts/e2e/` (nuovi file `tribunal_*`), `src/backend/tests/integration/test_tribunal_adversarial.py`, `README.md`, `CHANGELOG.md`, `docs/tribunale/test-report.md`. È l'unico task del Tribunale che tocca README e CHANGELOG, per evitare conflitti tra agenti.
Riferimenti: `scripts/e2e/doctor2_fake_llm.py`, `doctor2_stack.sh`, `doctor2_e2e.cjs` e `scripts/e2e/README.md`; `docs/doctor2/test-report.md` come modello.
I difetti trovati si correggono nel modulo che li contiene, segnalandolo nel report.
<!-- SECTION:NOTES:END -->
