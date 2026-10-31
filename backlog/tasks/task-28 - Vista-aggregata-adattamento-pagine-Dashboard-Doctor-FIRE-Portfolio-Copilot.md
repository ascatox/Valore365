---
id: TASK-28
title: 'Vista aggregata: adattamento pagine Dashboard, Doctor, FIRE, Portfolio, Copilot'
status: To Do
assignee: []
created_date: '2026-10-31T10:00:00Z'
labels:
  - frontend
  - vista-aggregata
dependencies: [TASK-27]
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Usare lo scope globale in tutte le pagine. Il FIRE abbandona la somma lato frontend e usa gli endpoint aggregati. La pagina Portfolio in vista aggregata è in sola lettura.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Dashboard e Doctor funzionano completamente in vista aggregata
- [ ] #2 FIRE usa lo scope globale e gli endpoint aggregati; rimossa la logica di somma e la chiave fireAggregatePortfolioIds
- [ ] #3 Portfolio: posizioni fuse e transazioni con colonna Portafoglio; disattivate con tooltip le azioni di scrittura (nuova transazione, ribilanciamento, target allocation, PAC, liquidità, CSV, modifica/clona/elimina)
- [ ] #4 Copilot riceve portfolio_ids dello scope corrente
- [ ] #5 Test delle pagine in modalità aggregata
<!-- AC:END -->
