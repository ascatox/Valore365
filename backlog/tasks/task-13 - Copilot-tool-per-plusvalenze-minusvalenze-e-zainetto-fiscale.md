---
id: TASK-13
title: 'Copilot: tool per plusvalenze, minusvalenze e zainetto fiscale'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - copilot
  - backend
  - fiscale
milestone: m-0
dependencies: []
priority: low
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le domande fiscali sono fra le più frequenti per un investitore italiano (quanto pago se vendo, posso compensare le minusvalenze), ma il Copilot non ha dati per rispondere e rischia di improvvisare. Le regole italiane sono specifiche: le plusvalenze da ETF sono redditi di capitale e non compensano le minusvalenze, che sono redditi diversi e scadono dopo 4 anni. Serve un calcolo deterministico esposto come tool, così il Copilot spiega numeri veri. Collegato a `backlog/tasks/fire-2-0-decumulo-fiscale.md`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un tool restituisce per anno plusvalenze e minusvalenze realizzate, distinguendo redditi di capitale e redditi diversi
- [ ] #2 Il tool restituisce le minusvalenze compensabili ancora disponibili, con la loro scadenza
- [ ] #3 Per una vendita ipotetica il tool stima l'imposta e indica quando le minusvalenze disponibili non sono compensabili
- [ ] #4 Le aliquote (26%, 12,5% per i titoli di Stato) sono configurate in un solo punto
- [ ] #5 Il prompt del Copilot indica di usare il tool per le domande fiscali e di dichiarare le semplificazioni del calcolo
- [ ] #6 Test sul calcolo con casi che includono ETF, azioni e titoli di Stato
<!-- AC:END -->
