---
id: TASK-83
title: 'PAC: calculate_pac_contribution dichiara allocato un importo non distribuito'
status: Done
assignee: []
created_date: '2026-11-11T09:00:00Z'
labels:
  - auditor
  - mcp
  - backend
milestone: m-1
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dall'Auditor dei calcoli (regola `B-PAC-SUM`, P1, marcata `known_defect: "TASK-83"` da TASK-79).

`calculate_pac_contribution` (`src/backend/app/copilot_tools.py`, `_calculate_pac_contribution`) distribuisce l'importo mensile solo sugli strumenti sottopesati. Quando nessuno strumento è sotto il proprio target (tutti a target o sopra, caso tipico con target che sommano meno di 100) la distribuzione resta vuota, ma il ramo «remaining» distribuisce il residuo solo sulle righe già presenti (nessuna) e poi azzera comunque `remaining`: il tool risponde con `distribution: []` e `total_allocated` pari all'intero importo. L'utente (e il Copilot) legge che 500 € sono stati allocati quando non è stato indicato alcuno strumento.

Evidenza (seed dell'Auditor su PostgreSQL 16, portafoglio 9105 «AUD Import» con target aggiunti `AUDEQ.MI` 60 e `AUDBD.MI` 30, pesi attuali 66,67 / 33,33, entrambi sopra il target):

```
python -m app.services.auditor --user auditor-seed-user --mode ci --rule B-PAC-SUM --portfolio 9105 --no-aggregate --no-instruments
fail B-PAC-SUM portfolio:9105 — Nel PAC la somma dei versamenti per strumento non è uguale all'importo indicato.
  distribution[*].amount_eur (calculate_pac_contribution {"portfolio_id": 9105, "monthly_amount": 500.0}): 0 → 500.0, tolleranza ±0,01 (somma su 0 righe = total_allocated)
```

Riprodotto anche in `src/backend/tests/unit/test_auditor_rules_rebalance.py::test_pac_sum_on_real_service_with_no_underweight_holding` (TASK-75) e, sul database del seed, in `src/backend/tests/integration/test_auditor_postgres.py::test_known_defect_pac_sum_reproduced_on_seed` (TASK-79). Il seed così com'è (9101, target 50/40/10 con `AUDBD.MI` sottopesato) non lo esercita: la regola lì dà `pass`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Con nessuno strumento sottopesato `calculate_pac_contribution` distribuisce l'importo secondo una regola dichiarata (per esempio in proporzione ai target) oppure risponde con distribuzione vuota, `total_allocated` 0 e una nota che spiega perché; in ogni caso `Σ distribution[].amount_eur == total_allocated` entro 0,01 €
- [x] #2 Test unitari sui due casi (tutti gli strumenti esattamente a target; target che sommano meno di 100 con tutti gli strumenti sopra il target); `test_pac_sum_on_real_service_with_no_underweight_holding` aggiornato al nuovo comportamento
- [x] #3 Rimosso `known_defect` da `B-PAC-SUM` in `src/backend/app/services/auditor/rules/rebalance_simulation.py`, riga tolta dalla sezione «Difetti noti» di `docs/auditor/rules.md`, e il test `test_known_defect_pac_sum_reproduced_on_seed` aggiornato perché la regola dia `pass`
<!-- AC:END -->
