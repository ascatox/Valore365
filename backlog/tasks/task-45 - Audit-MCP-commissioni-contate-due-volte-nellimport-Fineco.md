---
id: TASK-45
title: 'Audit MCP: commissioni contate due volte nell''import Fineco'
status: To Do
assignee: []
created_date: '2026-11-03T07:58:00Z'
labels:
  - audit-mcp
  - backend
  - dati
  - import
milestone: m-1
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso dalla riconciliazione del 2026-11-03. Nelle righe Fineco con commissioni il prezzo del file sembra già al netto/lordo della commissione (acquisti: prezzo = (controvalore + commissione)/quantità; vendite: prezzo netto), e l'import registra la commissione anche nel campo fees. Prove: id 5828 vende 1 VWRA a 153,89 con fees 19, mentre le righe gemelle dello stesso ordine (5829-5834) sono a 172,89 = 153,89 + 19; id 5835 EQQQ 658,73667 = (3 x 665,07 - 19)/3 con fees 19; id 5805 SE15 375 x 105,23067 = 39.461,50 incluso il costo di 19. Inoltre la quantità ricavata come controvalore/prezzo diventa non intera (374,99998, 2,99999998). Effetto: costo di carico gonfiato e proventi delle vendite ridotti dell'importo della commissione, una volta in più per ogni operazione (1,54-19 EUR).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Confermata la semantica di prezzo e controvalore nell'export Fineco su un estratto conto reale
- [ ] #2 L'import non conta due volte le commissioni (test con acquisto e vendita con commissioni)
- [ ] #3 Quantità intere quando l'export riporta una quantità intera
- [ ] #4 Query in sola lettura che stima l'effetto sui dati esistenti; eventuale correzione dei dati solo con un piano approvato
<!-- AC:END -->
