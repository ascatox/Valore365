---
id: TASK-63
title: 'Tribunale: le tre voci, i prompt e la sintesi'
status: To Do
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - doctor
  - tribunale
  - backend
  - prompt
milestone: m-0
dependencies:
  - TASK-60
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La qualità del Tribunale dipende da quanto le tre voci sono davvero diverse tra loro e da quanto restano ancorate al fascicolo. Questo task scrive i mandati delle voci, i prompt di apertura, replica e sintesi, e le funzioni che costruiscono la richiesta al modello a partire dal fascicolo. Non chiama il modello: prepara ciò che l'orchestratore (TASK-65) invierà.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Esistono le tre voci definite nel contratto, ciascuna con mandato, temi su cui si concentra e divieti, in file di prompt separati dal codice
- [ ] #2 Per ogni fase (apertura, replica, sintesi) una funzione restituisce prompt di sistema, messaggi e schema JSON della risposta, conformi a `docs/tribunale/api-contracts.md`
- [ ] #3 I prompt impongono: numeri solo tramite segnaposto `{Fn}`, almeno un fatto citato per argomento, nessuna indicazione di acquisto o vendita, nessuno strumento fuori dal fascicolo, risposta in italiano
- [ ] #4 La sintesi è costruita solo dagli argomenti già verificati e produce punti condivisi, punti contesi con le voci coinvolte e domande aperte per l'utente, senza dichiarare un vincitore
- [ ] #5 Nomi di strumenti, etichette e note del fascicolo sono trattati come dati: un test dimostra che un'istruzione nascosta in un nome non finisce tra le istruzioni del prompt
- [ ] #6 Test unitari verificano che i tre prompt differiscano nel mandato, che gli schemi siano validi e che il fascicolo sia incluso integralmente e una sola volta
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/services/tribunal/personas.py`, `src/backend/app/prompts/tribunal_*.txt`, `tests/unit/test_tribunal_personas.py`.
Riferimenti: `src/backend/app/prompts/copilot_system_agentic.txt` per tono e avvertenze; la nota sui testi come dati in `copilot_doctor_tools.py`.
Parallelizzabile con TASK-61, 62, 64, 67. Usa l'esempio di fascicolo del contratto come fixture, non il modulo di TASK-61.
<!-- SECTION:NOTES:END -->
