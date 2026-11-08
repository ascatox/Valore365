import json
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import text

from ..models import (
    CashBalanceResponse,
    CashBreakdown,
    CashCurrencyBreakdown,
    CashFlowTimelinePoint,
    CashFlowTimelineResponse,
    CashMovementCreate,
    TransactionCreate,
    TransactionListItem,
    TransactionRead,
)
from ..crypto import (
    csv_filename_blind_index,
    decrypt_field,
    decrypt_json_field,
    encrypt_field,
    encrypt_json_field,
)
from ._base import PortfolioData
from ._transactions import decrypt_notes
from ._cash_model import cash_delta, fold_cash
from ._scope import load_scope_portfolios


def _build_cash_breakdown(
    *,
    base_currency: str,
    opening_cash_balance: float,
    rows: list[dict],
) -> list[CashCurrencyBreakdown]:
    balances_by_currency: dict[str, float] = {}

    for row in rows:
        currency = str(row["trade_currency"])
        balances_by_currency[currency] = round(float(row["balance"]), 2)

    if opening_cash_balance:
        balances_by_currency[base_currency] = round(
            balances_by_currency.get(base_currency, 0.0) + float(opening_cash_balance),
            2,
        )

    return [
        CashCurrencyBreakdown(currency=currency, balance=round(balance, 2))
        for currency, balance in sorted(balances_by_currency.items())
    ]


# Short Italian explanation of the cash model, for the API and the MCP tools.
CASH_MODEL_NOTE = (
    "Liquidita' calcolata con lo stesso modello della performance: saldo iniziale + depositi "
    "+ dividendi netti + interessi + vendite (netto di commissioni/imposte) - prelievi - "
    "commissioni - acquisti (comprese commissioni/imposte), al cambio della data del movimento. "
    "La liquidita' non va mai sotto zero: un acquisto o un'uscita oltre la liquidita' disponibile "
    "e' coperto da un apporto implicito (implicit_contributions_total)."
)

# Components of the cash fold, in the order the breakdown lists them. Every
# amount is positive; the sign is in CASH_COMPONENT_SIGNS.
CASH_COMPONENT_SIGNS: dict[str, int] = {
    "opening_balance": 1,
    "deposits": 1,
    "withdrawals": -1,
    "dividends": 1,
    "interest": 1,
    "fees": -1,
    "buys": -1,
    "sells": 1,
    "implicit_contributions": 1,
}
_SIDE_COMPONENT = {
    "deposit": "deposits",
    "withdrawal": "withdrawals",
    "dividend": "dividends",
    "interest": "interest",
    "fee": "fees",
    "buy": "buys",
    "sell": "sells",
}


@dataclass(frozen=True)
class CashBalanceDetail:
    """Cash of one portfolio (or a sum of portfolios) in its base currency.

    ``balance``: the TASK-46 cash model folded over every transaction
    (TASK-49): opening ``cash_balance`` (cash before the first transaction) +
    deposits, net dividends, interest and net sell proceeds - withdrawals,
    fees and buys (fees/taxes included), each converted at the FX rate of its
    trade date, settled at the end of every day: a shortfall is an implicit
    contribution and cash never goes below 0. ``implicit_contributions``: the
    cumulative implicit contributions. ``components``: the positive amount of
    every component in base currency (signs in CASH_COMPONENT_SIGNS), adding
    up to ``balance``. ``fx_missing_currencies``: currencies of transactions
    with no rate on or before their trade date (converted at 1.0, so the
    balance is approximate). ``nominal_by_currency``: the same deltas summed
    per currency without conversion (opening cash and implicit contributions
    in the base currency).
    """

    balance: float
    fx_missing_currencies: list[str] = field(default_factory=list)
    nominal_by_currency: dict[str, float] = field(default_factory=dict)
    implicit_contributions: float = 0.0
    components: dict[str, float] = field(default_factory=dict)


def _cash_movement_nominal(side: str, quantity: float, price: float, taxes: float, fees: float = 0.0) -> float:
    """Signed change of cash of one transaction, in its own currency.

    The TASK-46 cash model (``_cash_model.cash_delta``): buys cost price x
    quantity + fees + taxes, sells bring the net proceeds, dividends are net
    of withholding taxes, the other cash sides move by their amount.
    """
    costs = (fees + taxes) if side in ("buy", "sell") else 0.0
    return cash_delta(side, quantity * price, costs, taxes)


def _cash_balance_detail(
    *,
    base_currency: str,
    opening_cash_balance: float,
    rows: list[dict],
    fx_rows: list[dict],
) -> CashBalanceDetail:
    """The one cash rule (TASK-47, TASK-49): the performance cash model, folded to today.

    Shared by summary.cash_balance, GET /cash-balance, the MCP/copilot tools,
    the aggregates, Monte Carlo and the rebalance. ``rows`` are every
    transaction of the portfolio in (trade_at, id) order, trades included.
    The opening balance is cash available before the first transaction (see
    ``_cash_model``). Every transaction in a non-base currency is converted at
    the rate of its trade date (last rate on or before it), like the
    valuation fold and the cost basis of the positions. A transaction without
    such a rate is converted at 1.0 and its currency is reported, never
    silently. O(n) in the number of transactions.
    """
    fx_series: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in fx_rows:
        fx_series[str(row["from_ccy"])].append((row["price_date"], float(row["rate"])))
    fx_dates = {ccy: [d for d, _ in series] for ccy, series in fx_series.items()}

    def fx_rate_on_or_before(currency: str, day: date | None) -> float | None:
        if currency == base_currency:
            return 1.0
        if day is None:
            return None
        series = fx_series.get(currency)
        dates = fx_dates.get(currency)
        if not series or not dates:
            return None
        idx = bisect_right(dates, day) - 1
        if idx < 0:
            return None
        return series[idx][1]

    opening = float(opening_cash_balance)
    nominal: dict[str, float] = defaultdict(float)
    if opening:
        nominal[base_currency] += opening
    components: dict[str, float] = {key: 0.0 for key in CASH_COMPONENT_SIGNS}
    components["opening_balance"] = opening
    missing: set[str] = set()
    deltas: list[tuple[date | None, float]] = []
    for row in rows:
        side = str(row["side"])
        component = _SIDE_COMPONENT.get(side)
        if component is None:
            continue
        trade_ccy = str(row["trade_currency"])
        amount = _cash_movement_nominal(
            side,
            float(row["quantity"]),
            float(row["price"]),
            float(row.get("taxes") or 0.0),
            float(row.get("fees") or 0.0),
        )
        nominal[trade_ccy] += amount
        fx_rate = fx_rate_on_or_before(trade_ccy, row.get("trade_date"))
        if fx_rate is None:
            missing.add(trade_ccy)
            fx_rate = 1.0
        delta = amount * fx_rate
        components[component] += delta * CASH_COMPONENT_SIGNS[component]
        deltas.append((row.get("trade_date"), delta))

    cash, implicit = fold_cash(deltas, opening)
    components["implicit_contributions"] = implicit
    if implicit:
        nominal[base_currency] += implicit

    return CashBalanceDetail(
        balance=round(cash, 2),
        fx_missing_currencies=sorted(missing),
        nominal_by_currency={ccy: round(v, 2) for ccy, v in nominal.items()},
        implicit_contributions=round(implicit, 2),
        components={key: round(value, 2) for key, value in components.items()},
    )


def _compute_cash_balance_base(
    *,
    base_currency: str,
    opening_cash_balance: float,
    rows: list[dict],
    fx_rows: list[dict],
) -> float:
    return _cash_balance_detail(
        base_currency=base_currency,
        opening_cash_balance=opening_cash_balance,
        rows=rows,
        fx_rows=fx_rows,
    ).balance


class UtilitiesMixin:
    def get_idempotency_response(self, *, idempotency_key: str, endpoint: str, user_id: str | None = None) -> dict | None:
        if user_id:
            query = """
                select response_json
                from api_idempotency_keys
                where idempotency_key = :idempotency_key and endpoint = :endpoint and owner_user_id = :user_id
            """
            params = {"idempotency_key": idempotency_key, "endpoint": endpoint, "user_id": user_id}
        else:
            query = """
                select response_json
                from api_idempotency_keys
                where idempotency_key = :idempotency_key and endpoint = :endpoint
            """
            params = {"idempotency_key": idempotency_key, "endpoint": endpoint}
        with self.engine.begin() as conn:
            row = conn.execute(text(query), params).mappings().fetchone()
        if row is None:
            return None
        return row["response_json"]

    def save_idempotency_response(self, *, idempotency_key: str, endpoint: str, response_payload: dict, user_id: str | None = None) -> None:
        owner_user_id = user_id or "dev-user"
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into api_idempotency_keys (idempotency_key, endpoint, response_json, owner_user_id)
                    values (:idempotency_key, :endpoint, cast(:response_json as jsonb), :owner_user_id)
                    on conflict (idempotency_key, endpoint, owner_user_id)
                    do update set response_json = excluded.response_json
                    """
                ),
                {
                    "idempotency_key": idempotency_key,
                    "endpoint": endpoint,
                    "response_json": json.dumps(response_payload),
                    "owner_user_id": owner_user_id,
                },
            )

    def get_portfolio_base_currency(self, portfolio_id: int, user_id: str | None = None) -> str:
        with self.engine.begin() as conn:
            if user_id:
                portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            else:
                row = conn.execute(
                    text("select id, base_currency, cash_balance from portfolios where id = :id"),
                    {"id": portfolio_id},
                ).mappings().fetchone()
                portfolio = PortfolioData(id=int(row["id"]), base_currency=str(row["base_currency"]), cash_balance=float(row["cash_balance"])) if row else None
            if portfolio is None:
                raise ValueError("Portfolio non trovato")
            return portfolio.base_currency

    def get_quote_currencies_for_assets(self, asset_ids: list[int]) -> dict[int, str]:
        if not asset_ids:
            return {}
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select id, quote_currency
                    from assets
                    where id = any(:asset_ids)
                    """
                ),
                {"asset_ids": asset_ids},
            ).mappings().all()
        return {int(r["id"]): str(r["quote_currency"]) for r in rows}

    def get_price_coverage(self, portfolio_id: int, days: int = 365, user_id: str | None = None) -> list[dict]:
        """Return price bar coverage stats for each asset in the portfolio target allocation."""
        with self.engine.begin() as conn:
            if user_id and self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")
            rows = conn.execute(
                text(
                    """
                    select
                        pta.asset_id,
                        a.symbol,
                        coalesce(a.name, a.symbol) as name,
                        count(pb.price_date) as bar_count,
                        min(pb.price_date) as first_bar,
                        max(pb.price_date) as last_bar
                    from portfolio_target_allocations pta
                    join assets a on a.id = pta.asset_id
                    left join price_bars_1d pb
                        on pb.asset_id = pta.asset_id
                        and pb.price_date >= current_date - :days
                    where pta.portfolio_id = :portfolio_id
                    group by pta.asset_id, a.symbol, a.name
                    order by a.symbol
                    """
                ),
                {"portfolio_id": portfolio_id, "days": days},
            ).mappings().all()

        return _coverage_items(rows, days)

    def get_price_coverage_multi(self, portfolio_ids: list[int], user_id: str, days: int = 365) -> list[dict]:
        """Price coverage of every asset in the target allocations of several portfolios.

        An asset targeted by more portfolios is listed once. Requires user_id
        (the scope is always validated: empty, not owned, mixed currency).
        """
        with self.engine.begin() as conn:
            scope_ids, _ = load_scope_portfolios(self, conn, portfolio_ids, user_id)
            rows = conn.execute(
                text(
                    """
                    with targeted as (
                        select distinct asset_id
                        from portfolio_target_allocations
                        where portfolio_id = any(:portfolio_ids)
                    )
                    select
                        t.asset_id,
                        a.symbol,
                        coalesce(a.name, a.symbol) as name,
                        count(pb.price_date) as bar_count,
                        min(pb.price_date) as first_bar,
                        max(pb.price_date) as last_bar
                    from targeted t
                    join assets a on a.id = t.asset_id
                    left join price_bars_1d pb
                        on pb.asset_id = t.asset_id
                        and pb.price_date >= current_date - :days
                    group by t.asset_id, a.symbol, a.name
                    order by a.symbol
                    """
                ),
                {"portfolio_ids": scope_ids, "days": days},
            ).mappings().all()
        return _coverage_items(rows, days)

    # ---- Feature 2: Cash Movements ----

    def create_cash_movement(self, payload: CashMovementCreate, user_id: str) -> TransactionRead:
        return self.create_transaction(
            TransactionCreate(
                portfolio_id=payload.portfolio_id,
                asset_id=payload.asset_id,
                side=payload.side,
                trade_at=payload.trade_at,
                quantity=payload.quantity,
                price=1.0,
                fees=0,
                taxes=0,
                trade_currency=payload.trade_currency,
                notes=payload.notes,
            ),
            user_id,
        )

    def get_computed_cash_balance(self, portfolio_id: int, user_id: str) -> CashBalanceResponse:
        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")

            # One rule with summary.cash_balance and the performance (TASK-47,
            # TASK-49): the cash model folded over every transaction, at the
            # trade-date FX, dividends net of taxes, cash floored at 0.
            detail = self._cash_balance_details(conn, [portfolio])[portfolio.id]
            breakdown = _build_cash_breakdown(
                base_currency=portfolio.base_currency,
                opening_cash_balance=0.0,
                rows=[
                    {"trade_currency": ccy, "balance": balance}
                    for ccy, balance in detail.nominal_by_currency.items()
                ],
            )
            total_cash = detail.balance

            # Recent cash movements (last 20)
            recent_rows = conn.execute(
                text(
                    """
                    select t.id, t.portfolio_id, t.asset_id, t.side, t.trade_at,
                           t.quantity::float8 as quantity, t.price::float8 as price,
                           t.fees::float8 as fees, t.taxes::float8 as taxes,
                           t.trade_currency, t.notes,
                           a.symbol, a.name as asset_name
                    from transactions t
                    left join assets a on a.id = t.asset_id
                    where t.portfolio_id = :portfolio_id
                      and t.side in ('deposit', 'withdrawal', 'dividend', 'fee', 'interest')
                    order by t.trade_at desc, t.id desc
                    limit 20
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()
            recent_notes = [decrypt_notes(conn, user_id, r["notes"]) for r in recent_rows]

        recent = [
            TransactionListItem(
                id=int(r["id"]),
                portfolio_id=int(r["portfolio_id"]),
                asset_id=int(r["asset_id"]) if r["asset_id"] is not None else None,
                side=str(r["side"]),
                trade_at=r["trade_at"],
                quantity=float(r["quantity"]),
                price=float(r["price"]),
                fees=float(r["fees"]),
                taxes=float(r["taxes"]),
                trade_currency=str(r["trade_currency"]),
                notes=note,
                symbol=r["symbol"],
                asset_name=r["asset_name"],
            )
            for r, note in zip(recent_rows, recent_notes)
        ]

        return CashBalanceResponse(
            portfolio_id=portfolio_id,
            total_cash=total_cash,
            currency_breakdown=breakdown,
            recent_movements=recent,
            fx_missing_currencies=detail.fx_missing_currencies,
            implicit_contributions_total=detail.implicit_contributions,
            cash_breakdown=CashBreakdown(**detail.components),
            cash_model_note=CASH_MODEL_NOTE,
        )

    def get_current_cash_balance_value(self, portfolio_id: int, user_id: str) -> float:
        return self.get_current_cash_balance_detail(portfolio_id, user_id).balance

    def get_current_cash_balance_detail(self, portfolio_id: int, user_id: str) -> CashBalanceDetail:
        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")
            return self._cash_balance_details(conn, [portfolio])[portfolio.id]

    def get_current_cash_balance_value_multi(self, portfolio_ids: list[int], user_id: str) -> float:
        """Combined current cash of several portfolios (sum of each balance)."""
        return self.get_current_cash_balance_detail_multi(portfolio_ids, user_id).balance

    def get_current_cash_balance_detail_multi(self, portfolio_ids: list[int], user_id: str) -> CashBalanceDetail:
        """Combined cash of several portfolios: summed balances, union of the missing FX currencies."""
        with self.engine.begin() as conn:
            _, portfolios = load_scope_portfolios(self, conn, portfolio_ids, user_id)
            details = self._cash_balance_details(conn, portfolios)
        if len(portfolios) == 1:
            return details[portfolios[0].id]
        nominal: dict[str, float] = defaultdict(float)
        for p in portfolios:
            for ccy, value in details[p.id].nominal_by_currency.items():
                nominal[ccy] += value
        components: dict[str, float] = defaultdict(float)
        for p in portfolios:
            for key, value in details[p.id].components.items():
                components[key] += value
        # Each portfolio keeps its own cash (the aggregate value is the sum of
        # the single-portfolio folds), so balances and implicit contributions add up.
        return CashBalanceDetail(
            balance=round(sum(details[p.id].balance for p in portfolios), 2),
            fx_missing_currencies=sorted({c for p in portfolios for c in details[p.id].fx_missing_currencies}),
            nominal_by_currency={ccy: round(v, 2) for ccy, v in nominal.items()},
            implicit_contributions=round(sum(details[p.id].implicit_contributions for p in portfolios), 2),
            components={key: round(value, 2) for key, value in components.items()},
        )

    def _cash_balance_values(self, conn, portfolios: list[PortfolioData]) -> dict[int, float]:
        return {pid: detail.balance for pid, detail in self._cash_balance_details(conn, portfolios).items()}

    def _cash_balance_details(self, conn, portfolios: list[PortfolioData]) -> dict[int, CashBalanceDetail]:
        """Cash balance for several portfolios from one connection.

        Computing them one at a time cost a checkout and three queries each, so
        listing N portfolios opened 1+N connections. The transactions (every
        side: the cash model of TASK-49 includes buys and sells) and FX rates
        for the whole set come back in two queries here, and each portfolio is
        folded from its own slice (O(n)).
        """
        if not portfolios:
            return {}

        base_by_portfolio = {p.id: p.base_currency for p in portfolios}

        tx_rows = conn.execute(
            text(
                """
                select portfolio_id,
                       side,
                       trade_at::date as trade_date,
                       quantity::float8 as quantity,
                       price::float8 as price,
                       fees::float8 as fees,
                       taxes::float8 as taxes,
                       trade_currency
                from transactions
                where portfolio_id = any(:portfolio_ids)
                order by trade_at asc, id asc
                """
            ),
            {"portfolio_ids": sorted(base_by_portfolio)},
        ).mappings().all()

        # The global ordering by (trade_at, id) survives the split, so each
        # portfolio's rows stay in the order the single-portfolio query gave.
        rows_by_portfolio: dict[int, list[dict]] = defaultdict(list)
        for row in tx_rows:
            rows_by_portfolio[int(row["portfolio_id"])].append(dict(row))

        fx_needed = sorted(
            {
                str(row["trade_currency"])
                for row in tx_rows
                if row["trade_currency"] is not None
                and str(row["trade_currency"]) != base_by_portfolio.get(int(row["portfolio_id"]))
            }
        )
        # Portfolios can have different base currencies, so fetch every needed
        # pair at once and hand each portfolio only the rates into its own base.
        fx_by_base: dict[str, list[dict]] = defaultdict(list)
        if fx_needed:
            max_trade_day = max(
                (row["trade_date"] for row in tx_rows if row["trade_date"] is not None),
                default=None,
            )
            if max_trade_day is not None:
                fx_rows = conn.execute(
                    text(
                        """
                        select from_ccy, to_ccy, price_date, rate::float8 as rate
                        from fx_rates_1d
                        where from_ccy = any(:from_ccy)
                          and to_ccy = any(:to_ccy)
                          and price_date <= :max_trade_day
                        order by from_ccy asc, price_date asc
                        """
                    ),
                    {
                        "from_ccy": fx_needed,
                        "to_ccy": sorted(set(base_by_portfolio.values())),
                        "max_trade_day": max_trade_day,
                    },
                ).mappings().all()
                for row in fx_rows:
                    fx_by_base[str(row["to_ccy"])].append(dict(row))

        return {
            p.id: _cash_balance_detail(
                base_currency=p.base_currency,
                opening_cash_balance=p.cash_balance,
                rows=rows_by_portfolio.get(p.id, []),
                fx_rows=fx_by_base.get(p.base_currency, []),
            )
            for p in portfolios
        }

    def get_cash_flow_timeline(self, portfolio_id: int, user_id: str) -> CashFlowTimelineResponse:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")

            rows = conn.execute(
                text(
                    """
                    select trade_at::date as trade_date,
                           side,
                           -- dividends net of withholding taxes (TASK-47)
                           sum(quantity * price
                               - case when side = 'dividend' then coalesce(taxes, 0) else 0 end)::float8 as total
                    from transactions
                    where portfolio_id = :portfolio_id
                      and side in ('deposit', 'withdrawal', 'dividend', 'fee', 'interest')
                    group by trade_at::date, side
                    order by trade_date asc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

        daily: dict[str, dict[str, float]] = {}
        for r in rows:
            d = r["trade_date"].isoformat()
            if d not in daily:
                daily[d] = {"deposits": 0.0, "withdrawals": 0.0, "dividends": 0.0, "fees": 0.0, "interest": 0.0}
            side = str(r["side"])
            amount = float(r["total"])
            if side == "deposit":
                daily[d]["deposits"] += amount
            elif side == "withdrawal":
                daily[d]["withdrawals"] += amount
            elif side == "dividend":
                daily[d]["dividends"] += amount
            elif side == "fee":
                daily[d]["fees"] += amount
            elif side == "interest":
                daily[d]["interest"] += amount

        points: list[CashFlowTimelinePoint] = []
        cumulative = 0.0
        for d in sorted(daily.keys()):
            entry = daily[d]
            cumulative += entry["deposits"] + entry["dividends"] + entry["interest"] - entry["withdrawals"] - entry["fees"]
            points.append(CashFlowTimelinePoint(
                date=d,
                cumulative_cash=round(cumulative, 2),
                deposits=round(entry["deposits"], 2),
                withdrawals=round(entry["withdrawals"], 2),
                dividends=round(entry["dividends"], 2),
                fees=round(entry["fees"], 2),
                interest=round(entry["interest"], 2),
            ))

        return CashFlowTimelineResponse(portfolio_id=portfolio_id, points=points)

    # ---- Feature 3: CSV Import ----

    def create_csv_import_batch(
        self,
        portfolio_id: int,
        user_id: str,
        filename: str | None,
        total_rows: int,
        valid_rows: int,
        error_rows: int,
        preview_data: list[dict] | dict,
    ) -> int:
        # TASK-57: file name and preview are encrypted at rest; the duplicate
        # detection reads the plaintext source_sha256 column and the file
        # name blind index instead.
        source_sha256 = preview_data.get("source_sha256") if isinstance(preview_data, dict) else None
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")
            row = conn.execute(
                text(
                    """
                    insert into csv_import_batches (
                      portfolio_id, owner_user_id, original_filename, original_filename_bidx, source_sha256,
                      total_rows, valid_rows, error_rows, preview_data
                    )
                    values (
                      :portfolio_id, :user_id, :filename, :filename_bidx, :source_sha256,
                      :total_rows, :valid_rows, :error_rows, cast(:preview_data as jsonb)
                    )
                    returning id
                    """
                ),
                {
                    "portfolio_id": portfolio_id,
                    "user_id": user_id,
                    "filename": encrypt_field(conn, "csv_import_batches", "original_filename", user_id, filename),
                    "filename_bidx": csv_filename_blind_index(filename),
                    "source_sha256": source_sha256,
                    "total_rows": total_rows,
                    "valid_rows": valid_rows,
                    "error_rows": error_rows,
                    "preview_data": json.dumps(
                        encrypt_json_field(conn, "csv_import_batches", "preview_data", user_id, preview_data)
                    ),
                },
            ).fetchone()
        if row is None:
            raise ValueError("Impossibile creare batch CSV")
        return int(row.id)

    def get_csv_import_batch(self, batch_id: int, user_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select id, portfolio_id, status, original_filename, total_rows, valid_rows, error_rows, preview_data, created_at, committed_at
                    from csv_import_batches
                    where id = :batch_id and owner_user_id = :user_id
                    """
                ),
                {"batch_id": batch_id, "user_id": user_id},
            ).mappings().fetchone()
            if row is None:
                return None
            batch = dict(row)
            batch["original_filename"] = decrypt_field(
                conn, "csv_import_batches", "original_filename", user_id, batch["original_filename"]
            )
            batch["preview_data"] = decrypt_json_field(
                conn, "csv_import_batches", "preview_data", user_id, batch["preview_data"]
            )
        return batch

    def commit_csv_import_batch(
        self,
        batch_id: int,
        user_id: str,
        rows: list[tuple[int, TransactionCreate]],
    ) -> list[int] | None:
        """Claim a pending batch and insert its transactions in ONE database transaction.

        The claim is a conditional update (status pending -> committed): of two
        concurrent or repeated commits only one can win, the other gets None
        and inserts nothing. Any failure while inserting rolls back everything,
        claim included, so the batch stays pending. ``rows`` pairs each payload
        with its row number in the file, used in the error message.
        """
        with self.engine.begin() as conn:
            claimed = conn.execute(
                text(
                    """
                    update csv_import_batches
                    set status = 'committed', committed_at = now()
                    where id = :batch_id and owner_user_id = :user_id and status = 'pending'
                    returning id
                    """
                ),
                {"batch_id": batch_id, "user_id": user_id},
            ).fetchone()
            if claimed is None:
                return None
            inserted_ids: list[int] = []
            for row_number, payload in rows:
                try:
                    inserted_ids.append(self._insert_transaction(conn, payload, user_id).id)
                except ValueError as exc:
                    raise ValueError(f"Riga {row_number}: {exc}") from exc
            return inserted_ids

    def find_committed_csv_import_batches(
        self,
        portfolio_id: int,
        user_id: str,
        filename: str | None,
        source_sha256: str | None,
    ) -> list[dict]:
        """Committed batches of this portfolio with the same file name or the same content hash."""
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select id, original_filename, committed_at,
                           coalesce(source_sha256 = :source_sha256, false) as same_content
                    from csv_import_batches
                    where portfolio_id = :portfolio_id
                      and owner_user_id = :user_id
                      and status = 'committed'
                      and (
                        original_filename_bidx = :filename_bidx
                        or source_sha256 = :source_sha256
                        -- legacy rows not yet backfilled (no blind index, plaintext name)
                        or (original_filename_bidx is null and original_filename = :filename)
                      )
                    order by committed_at desc nulls last, id desc
                    limit 20
                    """
                ),
                {
                    "portfolio_id": portfolio_id,
                    "user_id": user_id,
                    "filename": filename,
                    "filename_bidx": csv_filename_blind_index(filename),
                    "source_sha256": source_sha256,
                },
            ).mappings().all()
            batches = [dict(row) for row in rows]
            for batch in batches:
                batch["original_filename"] = decrypt_field(
                    conn, "csv_import_batches", "original_filename", user_id, batch["original_filename"]
                )
        return batches

    def cancel_csv_import_batch(self, batch_id: int, user_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    update csv_import_batches
                    set status = 'cancelled'
                    where id = :batch_id and owner_user_id = :user_id and status = 'pending'
                    """
                ),
                {"batch_id": batch_id, "user_id": user_id},
            )


def _coverage_items(rows, days: int) -> list[dict]:
    # ~252 trading days per 365 calendar days
    expected_bars = int(days * 252 / 365)

    result = []
    for r in rows:
        bar_count = int(r["bar_count"])
        coverage_pct = round(bar_count / expected_bars * 100, 1) if expected_bars > 0 else 0.0
        result.append({
            "asset_id": int(r["asset_id"]),
            "symbol": str(r["symbol"]),
            "name": str(r["name"]),
            "bar_count": bar_count,
            "first_bar": r["first_bar"],
            "last_bar": r["last_bar"],
            "expected_bars": expected_bars,
            "coverage_pct": min(coverage_pct, 100.0),
        })
    return result
