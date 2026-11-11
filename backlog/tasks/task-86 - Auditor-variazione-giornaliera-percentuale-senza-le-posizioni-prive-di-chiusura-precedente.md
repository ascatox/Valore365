---
id: TASK-86
title: 'Auditor: variazione giornaliera percentuale senza le posizioni prive di chiusura precedente'
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
Trovato dall'agente settimanale dell'Auditor nella prova a secco del 2026-11-11 (sospetto `S-2026-11-11-03`, report `docs/auditor/reports/2026-11-11-prova-a-secco.md`). Severità proposta P2 (trasparenza; numero mostrato in riepilogo, Copilot e MCP).

`day_change_pct` del riepilogo (`app/repository/_summary.py`) è `day_change / previous_market_value`. Una posizione con prezzo fermo da oltre 7 giorni contribuisce 0 ma **resta** nel denominatore (commento nel codice e `docs/audit-mcp-2026-11/methodology.md` §9: toglierla «ridurrebbe il denominatore e gonfierebbe day_change_pct»). Una posizione **senza chiusura precedente** (una sola barra, nessun tick) esce invece dal ciclo con `continue` prima di `previous_market_value += ...`: esce anche dal denominatore, e la percentuale si gonfia proprio come il codice vuole evitare. Nessuna nota lo dichiara (`data_quality_note` cita solo il prezzo fermo).

Evidenza riproducibile (seed dell'Auditor, portafoglio 9107: `AUDSTL.MI` fermo, `AUDEQ.MI` valido, `AUDNPC.MI` 5.000 € senza chiusura precedente):

```
python3 scripts/auditor/mcp_call.py get_portfolio_summary '{"portfolio_id": 9107}'
→ "market_value": 16000.0, "day_change": -14.11, "day_change_pct": -0.13
python3 scripts/auditor/mcp_call.py get_day_movers '{"portfolio_id": 9107}'
→ "valid_positions": 1, "excluded_stale": 1, "excluded_no_previous_close": 1
```

Ricalcolo dai valori di `get_positions` (valore / (1 + variazione %)): `AUDEQ.MI` 5.014,04 + `AUDSTL.MI` 6.011,42 = 11.025,46 € → −14,11 / 11.025,46 = −0,128 % (−0,13, quello mostrato). Con `AUDNPC.MI` nel denominatore a variazione nulla, come le quotazioni ferme: −14,11 / 16.025,46 = −0,088 % (−0,09). Nella vista aggregata 9101…9107 l'effetto è −0,126 % contro −0,123 % (−0,13 contro −0,12).

Deduplica: le regole C-DAYMOVERS-* verificano solo `get_day_movers`; TASK-33 e TASK-44 hanno trattato la variazione della singola posizione (`previous_close_available`), non il denominatore del riepilogo; `audit-findings.md` C3 documenta il denominatore «valore precedente delle posizioni» senza questo caso.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Una posizione senza chiusura precedente resta nel denominatore di `day_change_pct` con contributo nullo (come una quotazione ferma), oppure il riepilogo dichiara in una nota le posizioni escluse e il perimetro della percentuale; `methodology.md` §9 aggiornata
- [ ] #2 Test unitario in `tests/unit/test_summary_day_change.py` con una posizione senza chiusura precedente
- [ ] #3 Attivata la regola proposta `C-DAYCHANGE-DENOMINATOR` (bozza nel report del 2026-11-11), con scheda in `docs/auditor/rules.md` e prova su 9107
<!-- AC:END -->
