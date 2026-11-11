---
id: TASK-84
title: 'Auditor: il Doctor legge il saldo iniziale come liquidità attuale'
status: To Do
assignee: []
created_date: '2026-11-11T12:00:00Z'
labels:
  - auditor
  - backend
milestone: m-1
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dall'agente settimanale dell'Auditor nella prova a secco del 2026-11-11 (sospetto `S-2026-11-11-01`, report `docs/auditor/reports/2026-11-11-prova-a-secco.md`). Severità proposta P1 (numero incoerente fra tool).

Lo snapshot del Doctor (`app/services/doctor_policy/snapshot.py`, `_load_scope` → `build_snapshot`, `cash_value=cash_balance + cash_positions`) somma `portfolios.cash_balance` dei portafogli dello scope. Da TASK-49 quella colonna è il **saldo di apertura** (liquidità prima della prima transazione, `cash_breakdown.opening_balance`), non la liquidità attuale: riepilogo, `get_cash_balance`, ribilanciamento, Monte Carlo e vista aggregata usano il modello di liquidità della performance (`get_current_cash_balance_detail`). Il Doctor e lo Scenario Lab vedono quindi 0 € di liquidità dove l'utente ne ha 9.256,50 €; con `constraints.use_cash_balance` (esposto dai tool MCP e dal Copilot) uno scenario finanziabile risulta impossibile e chiede nuova liquidità che non serve.

Evidenza riproducibile (seed dell'Auditor, `scripts/auditor/agent_stack.sh start`):

```
python3 scripts/auditor/mcp_call.py get_cash_balance '{"portfolio_id": 9101}'
→ "total_cash": 9256.5, "cash_breakdown": {"opening_balance": 0.0, "deposits": 100000.0, ...}
python3 scripts/auditor/mcp_call.py build_doctor_scenario '{"portfolio_id": 9101, "mode": "manual", "operations": [{"symbol": "AUDBD.MI", "action": "buy", "amount": 5000}], "constraints": {"use_cash_balance": true}}'
→ "feasible": false, "infeasible_code": "insufficient_cash",
  "infeasible_reason": "Gli acquisti (5.000 € con i costi) superano la liquidità disponibile (0 €): mancano 5.000 €.",
  "required_new_cash": 5000.0, "before": {"invested_value": 100000.0, "cash_value": 0.0, "total_value": 100000.0, ...}
```

Atteso: `before.cash_value` = 9.256,50 (= `get_cash_balance.total_cash`), `before.total_value` = 109.256,50 (= `market_value + cash_balance` del riepilogo), scenario fattibile con 4.256,50 € che restano in cassa. Stesso esito su tutti i portafogli non vuoti del seed (`cash_value` 0 contro 8.144,00 / 2.492,00 / 3.705,97 / 5.545,00 / 4.047,00) e sull'aggregato (0 contro 33.190,47). Le metriche del Doctor non cambiano (escludono la liquidità per D02), cambiano `cash_value`, `total_value`, la fattibilità e `required_new_cash` dello Scenario Lab.

Deduplica: nessuna regola confronta la liquidità del Doctor (D-CASH-CONSISTENCY confronta solo riepilogo e saldo di cassa); TASK-49 ha allineato riepilogo, ribilanciamento e Monte Carlo ma non lo snapshot del Doctor; OP-15 di `docs/doctor2/open-decisions.md` riguarda il default di `use_cash_balance`, non il valore letto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Lo snapshot del Doctor usa come liquidità dello scope la stessa liquidità del riepilogo (modello della performance, singolo portafoglio e aggregato), più le posizioni di tipo cash
- [ ] #2 Sul seed dell'Auditor `build_doctor_scenario` 9101 con acquisto di 5.000 € e `use_cash_balance` è fattibile e `before.cash_value` = 9.256,50; test unitario e di integrazione
- [ ] #3 Attivata la regola proposta `D-DOCTOR-CASH` (bozza nel report del 2026-11-11) in `rules/consistency.py`, con scheda in `docs/auditor/rules.md` e voce nella colonna «Prova»
<!-- AC:END -->
