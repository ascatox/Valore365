---
id: TASK-90
title: 'Auditor: il PAC con un importo grande supera il target e trascura lo strumento che diventa sottopesato'
status: To Do
assignee: []
created_date: '2026-11-11T18:30:00Z'
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
Trovato dall'agente settimanale dell'Auditor nella sessione del 2026-11-11 (sospetto `S-2026-11-11-13`, report `docs/auditor/reports/2026-11-11.md`). Severità proposta P1 (importi di acquisto incoerenti con il target e con `calculate_rebalance_orders`).

`calculate_pac_contribution` ripartisce il versamento in proporzione allo scostamento attuale in punti percentuali, calcolato sulla base prima del versamento, solo fra gli strumenti oggi sottopesati e senza tetto al fabbisogno. Quando l'importo è grande rispetto al portafoglio (caso normale per un portafoglio piccolo o appena aperto) uno strumento viene portato oltre il proprio target, mentre quello che il versamento rende sottopesato non riceve nulla. Per qualunque importo, uno strumento poco sottopesato riceve meno di quanto serve a mantenere il suo peso e si allontana dal target.

Evidenza riproducibile (seed dell'Auditor, portafoglio 9101, target `AUDEQ.MI` 50 / `AUDBD.MI` 40 / `AUDTECH.DE` 10, base 109.256,50 €):

```
python3 scripts/auditor/mcp_call.py calculate_pac_contribution '{"portfolio_id": 9101, "monthly_amount": 100000}'
→ AUDBD.MI   amount_eur 96228.93  current_weight 18.31  target_weight 40.0  new_weight_after 55.54
  AUDTECH.DE amount_eur  3771.07  current_weight  9.15  target_weight 10.0  new_weight_after  6.58
  (AUDEQ.MI assente: 70.000 / 209.256,50 = 33,45 % contro un target di 50)
python3 scripts/auditor/mcp_call.py calculate_pac_contribution '{"portfolio_id": 9101, "monthly_amount": 45000}'
→ AUDBD.MI 43303.02 → 41.04 ; AUDTECH.DE 1696.98 → 7.58
python3 scripts/auditor/mcp_call.py calculate_pac_contribution '{"portfolio_id": 9101, "monthly_amount": 500}'
→ AUDBD.MI 481.14 → 18.66 ; AUDTECH.DE 18.86 → 9.13 (era 9.15, target 10)
python3 scripts/auditor/mcp_call.py calculate_rebalance_orders '{"portfolio_id": 9101, "mode": "buy_only", "available_cash": 100000}'
→ AUDBD.MI 63702.6 → 40.0 ; AUDEQ.MI 34628.25 → 50.0 ; AUDTECH.DE 10925.65 → 10.0
```

Ricalcolo indipendente: sulla base dopo il versamento (209.256,50 €) i fabbisogni sono 34.628,25 / 63.702,60 / 10.925,65 € (gli stessi importi del ribilanciamento `buy_only`). Con 100.000 € il PAC lascia uno scostamento assoluto totale di 35,51 pp (16,55 + 15,54 + 3,42) contro 36,61 pp di partenza; una ripartizione in proporzione al fabbisogno ne lascerebbe circa 4,4. `AUDBD.MI` supera il 40 % da 42.153 € in su (38,6 % della base).

Ipotesi di causa (non una correzione): `app/copilot_tools.py:_calculate_pac_contribution`, `drift = current_w − target` sulla base attuale e quote proporzionali al solo scostamento.

Deduplica: B-PAC-SUM verifica solo la somma, B-PAC-UNDERWEIGHT-ONLY solo il peso attuale, B-DRIFT-REBALANCE-WEIGHTS la base dei pesi; TASK-83 e TASK-85 riguardano l'importo non distribuito e la base dei pesi; la regola di ripartizione del PAC non è descritta in `docs/audit-mcp-2026-11/methodology.md` §7 né in `decisions.md`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decisione del proprietario sulla regola di ripartizione del PAC (per esempio in proporzione al fabbisogno sulla base dopo il versamento, con tetto al fabbisogno di ogni strumento), scritta in `docs/audit-mcp-2026-11/methodology.md` §7
- [ ] #2 `calculate_pac_contribution` non porta alcuno strumento oltre il proprio peso obiettivo quando un altro resta sotto, e considera gli strumenti che il versamento rende sottopesati; con 100.000 € su 9101 nessun `new_weight_after` supera il `target_weight`
- [ ] #3 Test unitario con un versamento piccolo, uno pari alla base e uno superiore al fabbisogno totale; verifica sul portafoglio 9101 del seed
- [ ] #4 Attivata la regola proposta `B-PAC-NO-OVERSHOOT` (bozza nel report del 2026-11-11), con scheda in `docs/auditor/rules.md` e prova su 9101
<!-- AC:END -->
