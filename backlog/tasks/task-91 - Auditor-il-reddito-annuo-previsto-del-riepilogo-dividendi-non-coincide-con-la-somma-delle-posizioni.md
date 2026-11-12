---
id: TASK-91
title: 'Auditor: il reddito annuo previsto del riepilogo dividendi non coincide con la somma delle posizioni'
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
Trovato dall'agente settimanale dell'Auditor nella sessione del 2026-11-11 (sospetto `S-2026-11-11-14`, report `docs/auditor/reports/2026-11-11.md`). Severità proposta P2 (coerenza secondaria fra tool).

`get_dividend_summary` calcola `projected_annual_income_eur` come valore di mercato × rendimento medio, e il rendimento medio dai pesi delle posizioni già arrotondati a 2 decimali. Il totale non coincide né con la somma delle righe `top_yielding_positions[].annual_income_eur` dello stesso output né con `current_annual_dividends_gross_eur` di `get_income_projection`, che è la stessa grandezza.

Evidenza riproducibile (seed dell'Auditor):

```
python3 scripts/auditor/mcp_call.py get_dividend_summary '{"portfolio_id": 9102}'
→ "portfolio_weighted_yield_pct": 3.13, "projected_annual_income_eur": 1324.12,
  righe: AUDHY.DE 712.5, AUDGOV.MI 450.0, AUDBTP 161.6   (somma 1324.10)
python3 scripts/auditor/mcp_call.py get_income_projection '{"portfolio_id": 9102}'
→ "current_annual_dividends_gross_eur": 1324.1
python3 scripts/auditor/mcp_call.py get_dividend_summary '{"portfolio_id": 9104}'
→ "projected_annual_income_eur": 280.79, riga AUDUK.L 280.8
python3 scripts/auditor/mcp_call.py get_income_projection '{"portfolio_id": 9104}'
→ "current_annual_dividends_gross_eur": 280.8
```

Ricalcolo: 18.000 × 2,5 % + 14.250 × 5,0 % + 10.100 × 1,6 % = 1.324,10; 9.360 × 3,0 % = 280,80. I valori mostrati si ottengono con i pesi arrotondati: (42,50 × 2,5 + 33,65 × 5,0 + 23,85 × 1,6) / 100 × 42.350 = 1.324,12; 34,06 × 3,0 / 100 × 27.480 = 280,79. L'errore cresce con il valore del portafoglio e il numero di posizioni (fino a 0,005 pp di peso × rendimento × valore per posizione).

Ipotesi di causa (non una correzione): `app/copilot_tools.py:_get_dividend_summary`, `weighted_yield += dy * (p.weight / 100)` con `Position.weight` arrotondato, poi `total_mv * weighted_yield / 100`.

Deduplica: C-INCOME-BUCKETS-SUM e C-INCOME-CLASS-RECOMPUTE leggono solo `get_income_projection`, C-DIV-CURRENCY solo i dividendi incassati; nessun task sul reddito previsto del riepilogo dividendi (controllati TASK-36, TASK-44).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `projected_annual_income_eur` di `get_dividend_summary` coincide al centesimo con `current_annual_dividends_gross_eur` di `get_income_projection` e con la somma delle righe quando l'elenco è completo (9102: 1.324,10; 9104: 280,80); `projected_monthly_income_eur` ne è un dodicesimo
- [ ] #2 Test unitario con pesi che non si arrotondano esattamente; verifica sui portafogli 9102 e 9104 del seed
- [ ] #3 Attivata la regola proposta `C-DIV-PROJECTION-MATCH` (bozza nel report del 2026-11-11), con scheda in `docs/auditor/rules.md` e prova su 9102 e 9104
<!-- AC:END -->
