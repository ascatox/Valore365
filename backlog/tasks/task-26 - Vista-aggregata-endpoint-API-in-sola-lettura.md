---
id: TASK-26
title: 'Vista aggregata: endpoint API in sola lettura'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T10:00:00Z'
labels:
  - backend
  - vista-aggregata
dependencies: [TASK-25]
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Esporre la vista aggregata via API seguendo il precedente di GET /portfolios/aggregate/decumulation: rotte /portfolios/aggregate/... con query portfolio_ids ripetuto, registrate prima delle rotte {portfolio_id}.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Endpoint aggregati per summary, positions, allocation, timeseries, intraday-timeseries, performers, performance/* (summary, twr, mwr, timeseries, monthly, yearly, drawdown, rolling, hall-of-fame), monte-carlo, xray, health, stress-test, transactions, data-coverage
- [ ] #2 Le transazioni aggregate riportano portfolio_id e portfolio_name per riga
- [ ] #3 Errori coerenti: 400 per valute diverse o lista vuota, 404 per portafogli non dell'utente
- [ ] #4 Test delle rotte (inclusa la precedenza della rotta aggregate sulle rotte con id)
<!-- AC:END -->
