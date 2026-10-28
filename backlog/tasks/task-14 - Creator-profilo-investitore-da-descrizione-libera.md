---
id: TASK-14
title: 'Creator: profilo investitore da descrizione libera'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - creator
  - frontend
  - backend
milestone: m-0
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il percorso Profilo guidato del Creator e i campi di profilo dichiarato per portafoglio sono pianificati in `backlog/tasks/task-creator-pagine-mancanti.md` e `backlog/tasks/scheda-rendiconto-portafoglio.md`; questo task va fatto dopo di loro. Un questionario a scelta multipla costringe l'utente a tradurre da solo la propria situazione (età, obiettivi, scadenze) in categorie astratte. Permettere di descriverla a parole e precompilare le risposte rende il percorso più accessibile al target non esperto. Il passaggio dal profilo ai portafogli modello resta la mappatura deterministica del questionario: l'AI precompila, non raccomanda, per restare fuori dalla consulenza personalizzata.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Nel percorso Profilo guidato l'utente può scrivere una descrizione libera della propria situazione
- [ ] #2 Il sistema restituisce le risposte del questionario (orizzonte, rischio, obiettivo) in forma strutturata e validata, mostrate precompilate e modificabili
- [ ] #3 La scelta dei portafogli modello usa la stessa mappatura del questionario compilato a mano
- [ ] #4 Se l'AI non è disponibile resta solo il questionario manuale
- [ ] #5 Il testo libero dell'utente non viene salvato
- [ ] #6 Test con provider simulato su descrizioni chiare, ambigue e fuori tema
<!-- AC:END -->
