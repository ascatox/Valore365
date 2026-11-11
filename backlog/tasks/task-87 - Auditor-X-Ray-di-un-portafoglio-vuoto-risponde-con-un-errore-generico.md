---
id: TASK-87
title: 'Auditor: X-Ray di un portafoglio vuoto risponde con un errore generico'
status: To Do
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
Trovato dall'agente settimanale dell'Auditor nella prova a secco del 2026-11-11 (sospetto `S-2026-11-11-04`, report `docs/auditor/reports/2026-11-11-prova-a-secco.md`). Severità proposta P2 (caso limite, domanda 7 della metodologia).

Su un portafoglio senza posizioni `get_xray_summary` solleva `ValueError("Portafoglio non trovato o vuoto")` in `compute_portfolio_xray` (`app/services/portfolio_doctor/_xray.py`); `execute_tool` lo trasforma in un errore e il server MCP lo maschera con il messaggio generico «Errore nell'esecuzione del tool get_xray_summary», lo stesso di un guasto vero. Gli altri tool sullo stesso portafoglio rispondono con un output vuoto e leggibile (`get_stress_test` `scenarios: []`, `get_cost_breakdown` con campi null, `get_portfolio_health` punteggio 0 e livelli `unknown`, `build_doctor_scenario` `infeasible_code: "empty_portfolio"` con un motivo in italiano).

Evidenza riproducibile (seed dell'Auditor, portafoglio 9106 vuoto):

```
python3 scripts/auditor/mcp_call.py get_xray_summary '{"portfolio_id": 9106}'
→ {"error": "Errore nell'esecuzione del tool get_xray_summary"}     (codice di uscita 1)
python3 scripts/auditor/mcp_call.py get_xray_summary '{"portfolio_id": 9106}' --debug
→ ValueError: Portafoglio non trovato o vuoto (app/services/portfolio_doctor/_xray.py)
```

Deduplica: il comportamento è annotato in `docs/auditor/architecture.md`, Deviazioni TASK-78 (le regole decidono `empty_portfolio` da `get_positions` prima di leggere X-Ray), ma nessun task lo tratta; nessuna regola lo verifica (D-XRAY-SUMS va in `skip` su 9106).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `get_xray_summary` su un portafoglio vuoto risponde con un output vuoto dichiarato (coperture 0 o null, esposizioni vuote, nota) oppure con un errore esplicito «portafoglio senza posizioni», distinto dall'errore generico; stesso comportamento per l'aggregato composto solo da portafogli vuoti
- [ ] #2 Test unitario e verifica sul portafoglio 9106 del seed
- [ ] #3 Attivata la regola proposta `D-XRAY-EMPTY` (bozza nel report del 2026-11-11), con scheda in `docs/auditor/rules.md` e prova su 9106; aggiornata la nota delle Deviazioni TASK-78
<!-- AC:END -->
