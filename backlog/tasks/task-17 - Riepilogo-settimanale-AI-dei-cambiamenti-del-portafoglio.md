---
id: TASK-17
title: Riepilogo settimanale AI dei cambiamenti del portafoglio
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - doctor
  - backend
  - frontend
milestone: m-0
dependencies:
  - TASK-16
  - TASK-8
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Un elenco di cambiamenti tecnici (score -6, nuovo avviso di concentrazione) è poco leggibile per l'utente tipico. Tre frasi in italiano semplice, generate solo quando il rilevamento settimanale trova qualcosa, rendono l'informazione utile senza chiamare il modello ogni settimana per ogni portafoglio.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Il riepilogo viene generato solo se il rilevamento settimanale trova almeno un cambiamento
- [ ] #2 Il riepilogo ha al massimo 3 frasi e ogni numero citato supera il controllo dei numeri
- [ ] #3 L'utente vede il riepilogo nella dashboard e può disattivarlo nelle Impostazioni
- [ ] #4 La generazione usa la chiave server con un modello leggero configurabile; senza AI la dashboard mostra l'elenco dei cambiamenti senza testo generato
- [ ] #5 Test con provider simulato
<!-- AC:END -->
