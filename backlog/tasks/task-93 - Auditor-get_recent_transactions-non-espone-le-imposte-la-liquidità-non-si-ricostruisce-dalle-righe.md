---
id: TASK-93
title: 'Auditor: get_recent_transactions non espone le imposte, la liquidità non si ricostruisce dalle righe'
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
Trovato dall'agente settimanale dell'Auditor nella sessione del 2026-11-11 (sospetto `S-2026-11-11-16`, report `docs/auditor/reports/2026-11-11.md`). Severità proposta P2 (trasparenza: il saldo è corretto, la riga mostrata è incompleta).

Il modello della liquidità scala le imposte (`taxes`) da vendite e dividendi e le aggiunge agli acquisti (`methodology.md` §8), ma `get_recent_transactions` e `get_aggregate_recent_transactions` mostrano per ogni riga solo `total` (quantità × prezzo) e `fees`. Con gli importi mostrati la liquidità di `get_cash_balance` non si ricostruisce: manca l'input.

Evidenza riproducibile. Il seed non ha transazioni con imposte: l'esperimento si fa sul database dello stack e si annulla con `reseed`.

```
psql -h "$AGENT_DIR" -p 55450 -U postgres -d valore365_auditor -v ON_ERROR_STOP=1 <<'SQL'
insert into transactions (portfolio_id, asset_id, side, trade_at, quantity, price, fees, taxes, trade_currency, notes, owner_user_id)
select 9106, asset_id, side, (current_date - days_ago) + time '12:00', quantity, price, fees, taxes, 'EUR', null, 'auditor-seed-user'
from (values
  (null::bigint, 'deposit', 100, 1::numeric, 10000.00::numeric, 0::numeric, 0::numeric),
  (9101, 'buy', 90, 50, 90.00, 2.00, 0),
  (null, 'fee', 80, 1, 25.00, 0, 0),
  (null, 'interest', 70, 1, 12.00, 0, 0),
  (9101, 'dividend', 50, 1, 40.00, 0, 10.40),
  (null, 'withdrawal', 40, 1, 1000.00, 0, 0),
  (9101, 'sell', 30, 10, 95.00, 1.50, 3.00)
) as t(asset_id, side, days_ago, quantity, price, fees, taxes);
SQL
python3 scripts/auditor/mcp_call.py get_recent_transactions '{"portfolio_id": 9106}'
→ {"type": "sell", "quantity": 10.0, "price": 95.0, "total": 950.0, "currency": "EUR", "fees": 1.5}
  {"type": "dividend", "quantity": 1.0, "price": 40.0, "total": 40.0, "currency": "EUR", "fees": 0}   (nessun campo taxes)
python3 scripts/auditor/mcp_call.py get_cash_balance '{"portfolio_id": 9106}'
→ "total_cash": 5460.1, "cash_breakdown": {"deposits": 10000.0, "withdrawals": 1000.0, "dividends": 29.6,
  "interest": 12.0, "fees": 25.0, "buys": 4502.0, "sells": 945.5}
scripts/auditor/agent_stack.sh reseed
```

Ricalcolo dagli importi mostrati: 10.000 − (4.500 + 2) − 25 + 12 + 40 − 1.000 + (950 − 1,50) = 5.473,50 contro `total_cash` 5.460,10. La differenza di 13,40 € è la somma delle imposte non mostrate (10,40 sul dividendo, 3,00 sulla vendita); con le imposte il ricalcolo dà 5.460,10.

Ipotesi di causa (non una correzione): `app/copilot_tools.py:_get_recent_transactions` costruisce la riga con `total` e `fees` senza `taxes`.

Deduplica: D-CASH-CONSISTENCY confronta `cash_breakdown` con il riepilogo, non con le transazioni; D-DUP-TRANSACTIONS e D-TRADE-PRICE-SCALE leggono `ctx.transactions`; TASK-42, TASK-47 e TASK-49 riguardano il modello, non le righe mostrate; `docs/auditor/rules.md` §9 cita solo il limite delle 20 righe.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Le righe di `get_recent_transactions` e `get_aggregate_recent_transactions` espongono `taxes` (o un importo netto per riga dichiarato), così che la liquidità di `get_cash_balance` si ricostruisca dalle transazioni mostrate quando l'elenco è completo
- [ ] #2 Test unitario con una vendita e un dividendo con imposte
- [ ] #3 Il seed dell'Auditor contiene almeno una vendita e un dividendo con `taxes` diverso da 0 (proposta §6 del report)
- [ ] #4 Attivata la regola proposta `D-TX-CASH-RECONCILE` (bozza nel report del 2026-11-11), con scheda in `docs/auditor/rules.md`
<!-- AC:END -->
