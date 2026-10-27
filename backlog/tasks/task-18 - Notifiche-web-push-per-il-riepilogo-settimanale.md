---
id: TASK-18
title: Notifiche web push per il riepilogo settimanale
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - pwa
  - frontend
  - backend
milestone: m-0
dependencies:
  - TASK-17
priority: low
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il riepilogo settimanale è utile solo se l'utente apre l'app. La PWA ha già un service worker (`src/frontend/valore-frontend/src/pwa/`) ma non gestisce notifiche push. Una notifica quando è pronto un nuovo riepilogo riporta l'utente nell'app quando c'è qualcosa da vedere.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 L'utente può attivare e disattivare le notifiche dalle Impostazioni, con la richiesta di permesso del browser
- [ ] #2 Quando viene generato un nuovo riepilogo, l'utente iscritto riceve una notifica che apre la dashboard del portafoglio
- [ ] #3 Le iscrizioni scadute o revocate vengono rimosse
- [ ] #4 Nessuna notifica viene inviata a chi non l'ha attivata
- [ ] #5 Test backend per iscrizione e invio, con servizio push simulato
<!-- AC:END -->
