---
id: TASK-15
title: 'Rendiconto: commento del periodo generato con AI'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - rendiconto
  - backend
  - frontend
milestone: m-0
dependencies:
  - TASK-8
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
I rendiconti dei consulenti accompagnano i numeri con un commento che spiega cosa è successo nel periodo. La scheda rendiconto pianificata in `backlog/tasks/scheda-rendiconto-portafoglio.md` mostra i numeri ma non li racconta; questo task va fatto dopo di essa. Un paragrafo generato dai dati già calcolati (rendimento, contributo delle posizioni, benchmark, rischio dichiarato ed effettivo) aiuta l'utente non esperto a leggerli.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 La scheda rendiconto mostra un commento di massimo 5 frasi sul periodo selezionato
- [ ] #2 Il commento è generato solo da dati calcolati dal backend; ogni numero citato supera il controllo dei numeri, altrimenti il commento non viene mostrato
- [ ] #3 Il commento è incluso nell'export Markdown
- [ ] #4 Il commento è in cache per portafoglio e periodo e viene rigenerato solo quando i dati cambiano
- [ ] #5 Senza AI configurata la scheda funziona senza commento
- [ ] #6 Test con provider simulato, incluso il caso di un numero non verificato
<!-- AC:END -->
