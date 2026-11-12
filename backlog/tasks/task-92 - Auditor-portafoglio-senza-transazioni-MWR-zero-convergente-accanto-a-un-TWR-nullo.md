---
id: TASK-92
title: 'Auditor: portafoglio senza transazioni, MWR zero convergente accanto a un TWR nullo'
status: To Do
assignee: []
created_date: '2026-11-11T18:30:00Z'
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
Trovato dall'agente settimanale dell'Auditor nella sessione del 2026-11-11 (sospetto `S-2026-11-11-15`, report `docs/auditor/reports/2026-11-11.md`). Severità proposta P2 (caso limite, domande 4 e 7 della metodologia dell'agente).

Su un portafoglio senza capitale né movimenti `get_performance` restituisce il TWR nullo (come vuole `docs/audit-mcp-2026-11/methodology.md` §8: «senza valore iniziale `twr_pct` è `null` (non 0)») ma il MWR a 0,0 con `mwr_converged: true` e `mwr_null_reason: null`, cioè un rendimento dello 0,00 % presentato come calcolato. I due rendimenti della stessa finestra trattano lo stesso caso in modo opposto, e il motivo `non_calcolabile` previsto per un MWR nullo non viene usato.

Evidenza riproducibile (seed dell'Auditor, portafoglio 9106 vuoto):

```
python3 scripts/auditor/mcp_call.py get_performance '{"portfolio_id": 9106}'
→ "twr_1m": null, "mwr_1m": 0.0, "twr_3m": null, "mwr_3m": 0.0, "twr_ytd": null, "mwr_ytd": 0.0,
  "twr_1y": null, "mwr_1y": 0.0,
  "mwr_converged": {"1m": true, "3m": true, "ytd": true, "1y": true},
  "mwr_null_reason": {"1m": null, "3m": null, "ytd": null, "1y": null},
  "calculation_windows": {"1m": {"start_date": "2026-11-11", "end_date": "2026-11-11", "period_days": 1}, ...}
```

Ipotesi di causa (non una correzione): `app/services/performance_service.py:calculate_mwr`, ramo `start_value == 0 and not cashflows and end_value == 0` che restituisce `MWRResult(mwr_pct=0.0, converged=True)`.

Deduplica: D-PERF-RECOMPUTE, D-PERF-TOOL-MATCH e D-SUMMARY-PERFORMANCE-VALUE vanno in `skip`/`no_transactions` su 9106; TASK-46 e TASK-55 non trattano il portafoglio vuoto; la prova a secco del 2026-11-11 annota il comportamento nella copertura senza proporlo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Senza valore iniziale, valore finale e flussi nella finestra `mwr_*` è `null` con `mwr_null_reason` valorizzato (per esempio `non_calcolabile`), come il TWR; oppure il proprietario decide che 0,0 è voluto e lo dichiara in `performance_note` e nella metodologia §8
- [ ] #2 Stesso comportamento per la vista aggregata composta solo da portafogli senza transazioni e per l'endpoint REST della performance
- [ ] #3 Test unitario e verifica sul portafoglio 9106 del seed
- [ ] #4 Attivata la regola proposta `D-PERF-EMPTY-NULL` (bozza nel report del 2026-11-11), con scheda in `docs/auditor/rules.md` e prova su 9106
<!-- AC:END -->
