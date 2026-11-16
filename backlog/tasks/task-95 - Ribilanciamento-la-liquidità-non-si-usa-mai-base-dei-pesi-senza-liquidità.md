---
id: TASK-95
title: 'Ribilanciamento: la liquidità non si usa mai; base dei pesi senza liquidità'
status: To Do
assignee: []
created_date: '2026-11-16T20:00:00Z'
labels:
  - backend
  - frontend
  - auditor
milestone: m-1
dependencies:
  - TASK-85
  - TASK-88
  - TASK-90
priority: high
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Decisione del proprietario (2026-11-16): **la liquidità del portafoglio non deve mai essere usata per ribilanciare.** Sostituisce la base dei pesi decisa in TASK-85 (strumenti con target + liquidità attuale), applicata anche da TASK-88 e TASK-90.

Conseguenze:
- **Base dei pesi rispetto ai target**: solo il valore degli strumenti con target (liquidità esclusa), ovunque: `get_target_drift`, endpoint `GET /portfolios/{id}/target-drift`, tabella posizioni e card mobile, snapshot del Copilot, export Markdown, `calculate_what_if` (old/new drift), anteprima REST del ribilanciamento. Un solo numero ovunque, come prima, ma sulla nuova base.
- **Ribilanciamento** (`calculate_rebalance_orders`, `compute_rebalance_plan`, anteprima REST): gli acquisti sono finanziati solo dalle vendite; la liquidità esistente non viene mai spesa né conteggiata come disponibile. Un'eventuale nuova liquidità entra solo se l'utente la indica esplicitamente come importo nuovo (es. modalità `buy_only` con l'importo inserito), mai valorizzata d'ufficio con il saldo.
- **PAC** (`compute_pac_split`, TASK-90): la base dopo il versamento è strumenti con target + importo, senza la liquidità attuale; resta la regola «verso i target senza superarli, eccedenza in proporzione ai target». Con liquidità 0 il PAC continua a coincidere con `buy_only` dello stesso importo.
- **Scenario Lab**: in modalità ribilanciamento la liquidità non si usa; verificare `constraints.use_cash_balance` e il suo default (OP-15 in `docs/doctor2/open-decisions.md`) e allinearli alla decisione nella sola modalità ribilanciamento.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Base dei pesi senza liquidità in tutti i punti elencati, con un'unica funzione in `services/rebalance.py`; sul seed 9101 (70.000 / 20.000 / 10.000 €, target 50/40/10) i pesi sono 70 / 20 / 10 e gli scostamenti +20 / −20 / 0 ovunque
- [ ] #2 `calculate_rebalance_orders` e l'anteprima REST non spendono mai la liquidità esistente: in modalità ribilanciamento acquisti = vendite (meno i costi), liquidità invariata; nessun default che usa il saldo
- [ ] #3 PAC sulla base senza liquidità, comportamento di TASK-83 e TASK-90 invariato per il resto
- [ ] #4 Scenario Lab in modalità ribilanciamento senza uso della liquidità
- [ ] #5 Testi e tooltip nel frontend, descrizioni dei tool, `methodology.md` §7 e `docs/auditor/rules.md` aggiornati alla nuova base
- [ ] #6 Regole dell'Auditor adattate (B-REB-*, B-DRIFT-REBALANCE-WEIGHTS, B-PAC-*, D-DOCTOR-CASH se tocca), con una regola che fallisce se il ribilanciamento spende la liquidità; Auditor completo sul seed senza fallimenti
- [ ] #7 Suite unit, integration e frontend verdi
<!-- AC:END -->
