---
id: TASK-85
title: 'Auditor: scostamento dal target e ribilanciamento usano pesi diversi'
status: Done
assignee: []
created_date: '2026-11-11T12:00:00Z'
labels:
  - auditor
  - backend
milestone: m-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dall'agente settimanale dell'Auditor nella prova a secco del 2026-11-11 (sospetto `S-2026-11-11-02`, report `docs/auditor/reports/2026-11-11-prova-a-secco.md`). Severità proposta P2 (coerenza secondaria fra tool).

`get_target_drift` calcola il peso attuale sul valore delle sole posizioni; `calculate_rebalance_orders` (decisione 9 di `docs/audit-mcp-2026-11/decisions.md`) lo calcola sul totale con la liquidità. I due tool rispondono alla stessa domanda («il portafoglio è in linea con il target?», guida utente MCP) con pesi diversi per lo stesso strumento e lo stesso target, e `get_target_drift` non dichiara il denominatore.

Evidenza riproducibile (seed dell'Auditor, portafoglio 9101, target 50/40/10, liquidità 9.256,50):

```
python3 scripts/auditor/mcp_call.py get_target_drift '{"portfolio_id": 9101}'
→ AUDEQ.MI current_weight 70.0 drift 20.0; AUDBD.MI 20.0 / -20.0; AUDTECH.DE 10.0 / 0.0 (in linea)
python3 scripts/auditor/mcp_call.py calculate_rebalance_orders '{"portfolio_id": 9101}'
→ AUDEQ.MI current_weight_pct 64.07 (sell 15371.75); AUDBD.MI 18.31 (buy 23702.6); AUDTECH.DE 9.15 (buy 925.65), tolerance_pp 0.5
```

Ricalcolo: 70.000 / 100.000 = 70,00 % (drift) contro 70.000 / 109.256,50 = 64,07 % (ribilanciamento). `AUDTECH.DE` è «in linea» (drift 0,0) per un tool e 0,85 pp sotto il target, oltre la banda di 0,5 pp, per l'altro, che lo compra. Anche `calculate_pac_contribution` usa i pesi delle sole posizioni (`current_weight` 20,0 per `AUDBD.MI`).

Deduplica: nessuna regola confronta i due tool (B-PAC-UNDERWEIGHT-ONLY usa solo i simboli di `get_target_drift`); la decisione 9 riguarda solo il ribilanciamento; nessun task aperto su `get_target_drift`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decisione del proprietario (2026-11-11: stessa base del ribilanciamento, cioè il totale con la liquidità): `get_target_drift` (e il PAC) usano lo stesso denominatore del ribilanciamento, oppure dichiarano nell'output il proprio denominatore e la differenza rispetto a `calculate_rebalance_orders`
- [x] #2 Test unitario sul caso 9101 del seed (posizioni + liquidità con target 50/40/10)
- [x] #3 Attivata la regola proposta `B-DRIFT-REBALANCE-WEIGHTS` (bozza nel report del 2026-11-11), adattata alla decisione, con scheda in `docs/auditor/rules.md`
<!-- AC:END -->
