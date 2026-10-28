---
id: TASK-12
title: 'Import: transazioni dai rendiconti PDF dei broker'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - import
  - backend
  - frontend
milestone: m-0
dependencies:
  - TASK-11
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Molti broker italiani forniscono lo storico operazioni solo in PDF (fissati bollati, rendiconti periodici). Chi non ha un CSV oggi deve inserire le transazioni a mano. Con la mappatura AI dell'import tabellare già disponibile, l'estrazione dal PDF può riusare la stessa validazione e la stessa anteprima con conferma.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 L'utente può caricare un PDF testuale e vedere le transazioni estratte nella stessa anteprima dell'import CSV/XLSX
- [ ] #2 Le righe con campi mancanti o incerti sono evidenziate e non importabili finché non vengono corrette
- [ ] #3 Nessuna transazione viene salvata senza conferma
- [ ] #4 PDF scansionati (senza testo) o non riconosciuti mostrano un messaggio chiaro
- [ ] #5 Un limite di dimensione e di pagine del PDF è applicato e documentato
- [ ] #6 Test con PDF di esempio e provider simulato
<!-- AC:END -->
