---
id: TASK-16
title: 'Doctor: storico settimanale e rilevamento dei cambiamenti'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - doctor
  - backend
  - scheduler
milestone: m-0
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il Doctor dà una fotografia del momento: l'utente non sa se lo score è peggiorato, se è comparso un nuovo avviso o se lo scostamento dal target è cresciuto, a meno di ricordarselo. Salvare un'istantanea periodica e confrontarla con la precedente è la base per avvisare l'utente solo quando c'è qualcosa di nuovo. Il task è deterministico: nessuna AI.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un job settimanale dello scheduler salva per ogni portafoglio score, avvisi e scostamenti dal target del Doctor
- [ ] #2 Il confronto con l'istantanea precedente produce un elenco di cambiamenti rilevanti (variazione di score oltre soglia, avvisi nuovi o risolti, scostamento dal target oltre soglia)
- [ ] #3 Le soglie sono configurate in un solo punto
- [ ] #4 Un endpoint restituisce gli ultimi cambiamenti di un portafoglio
- [ ] #5 Migrazione DB e test del confronto
<!-- AC:END -->
