import json
from bisect import bisect_right
from collections import defaultdict
from datetime import date

from sqlalchemy import text

from ..models import (
    CashBalanceResponse,
    CashCurrencyBreakdown,
    CashFlowTimelinePoint,
    CashFlowTimelineResponse,
    CashMovementCreate,
    TransactionCreate,
    TransactionListItem,
    TransactionRead,
)
from ._base import PortfolioData


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


def _compute_cash_balance_base(
    *,
    base_currency: str,
    opening_cash_balance: float,
    rows: list[dict],
    fx_rows: list[dict],
) -> float:
    fx_series: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in fx_rows:
        fx_series[str(row["from_ccy"])].append((row["price_date"], float(row["rate"])))
    fx_dates = {ccy: [d for d, _ in series] for ccy, series in fx_series.items()}

    def fx_rate_on_or_before(currency: str, day: date | None) -> float:
        if currency == base_currency:
            return 1.0
        if day is None:
            return 1.0
        series = fx_series.get(currency)
        dates = fx_dates.get(currency)
        if not series or not dates:
            return 1.0
        idx = bisect_right(dates, day) - 1
        if idx < 0:
            return 1.0
        return series[idx][1]

    cash_balance = float(opening_cash_balance)
    for row in rows:
        side = str(row["side"])
        # Only explicit cash movements affect liquidity
        if side not in {"deposit", "withdrawal", "dividend", "fee", "interest"}:
            continue
        trade_day = row["trade_date"]
        trade_ccy = str(row["trade_currency"])
        quantity = float(row["quantity"])
        price = float(row["price"])
        fx_rate = fx_rate_on_or_before(trade_ccy, trade_day)
        amount_base = quantity * price * fx_rate

        if side in {"deposit", "interest", "dividend"}:
            cash_balance += amount_base
        elif side in {"withdrawal", "fee"}:
            cash_balance -= amount_base

    return round(cash_balance, 2)


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

            # Compute cash only from explicit cash movements (no buy/sell)
            rows = conn.execute(
                text(
                    """
                    select trade_currency,
                           coalesce(sum(case
                             when side in ('deposit', 'interest', 'dividend') then quantity * price
                             when side in ('withdrawal', 'fee') then -quantity * price
                             else 0
                           end), 0)::float8 as balance
                    from transactions
                    where portfolio_id = :portfolio_id
                      and side in ('deposit', 'withdrawal', 'dividend', 'fee', 'interest')
                    group by trade_currency
                    order by trade_currency
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

            breakdown = _build_cash_breakdown(
                base_currency=portfolio.base_currency,
                opening_cash_balance=portfolio.cash_balance,
                rows=[dict(r) for r in rows],
            )

            # Convert each currency to base currency using latest FX rates
            non_base_currencies = sorted(
                {b.currency for b in breakdown if b.currency != portfolio.base_currency}
            )
            fx_latest: dict[str, float] = {}
            if non_base_currencies:
                fx_rows = conn.execute(
                    text(
                        """
                        select distinct on (from_ccy) from_ccy, rate::float8 as rate
                        from fx_rates_1d
                        where from_ccy = any(:from_ccy) and to_ccy = :to_ccy
                        order by from_ccy, price_date desc
                        """
                    ),
                    {"from_ccy": non_base_currencies, "to_ccy": portfolio.base_currency},
                ).mappings().all()
                for r in fx_rows:
                    fx_latest[str(r["from_ccy"])] = float(r["rate"])

            total_cash = 0.0
            for b in breakdown:
                if b.currency == portfolio.base_currency:
                    total_cash += b.balance
                else:
                    total_cash += b.balance * fx_latest.get(b.currency, 1.0)
            total_cash = round(total_cash, 2)

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
                notes=r["notes"],
                symbol=r["symbol"],
                asset_name=r["asset_name"],
            )
            for r in recent_rows
        ]

        return CashBalanceResponse(
            portfolio_id=portfolio_id,
            total_cash=total_cash,
            currency_breakdown=breakdown,
            recent_movements=recent,
        )

    def get_current_cash_balance_value(self, portfolio_id: int, user_id: str) -> float:
        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")

            tx_rows = conn.execute(
                text(
                    """
                    select side,
                           trade_at::date as trade_date,
                           quantity::float8 as quantity,
                           price::float8 as price,
                           fees::float8 as fees,
                           taxes::float8 as taxes,
                           trade_currency
                    from transactions
                    where portfolio_id = :portfolio_id
                      and side in ('deposit', 'withdrawal', 'dividend', 'fee', 'interest')
                    order by trade_at asc, id asc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

            if not tx_rows:
                return round(float(portfolio.cash_balance), 2)

            fx_needed = sorted(
                {
                    str(row["trade_currency"])
                    for row in tx_rows
                    if row["trade_currency"] is not None and str(row["trade_currency"]) != portfolio.base_currency
                }
            )
            fx_rows = []
            if fx_needed:
                max_trade_day = max(row["trade_date"] for row in tx_rows if row["trade_date"] is not None)
                fx_rows = conn.execute(
                    text(
                        """
                        select from_ccy, price_date, rate::float8 as rate
                        from fx_rates_1d
                        where from_ccy = any(:from_ccy)
                          and to_ccy = :to_ccy
                          and price_date <= :max_trade_day
                        order by from_ccy asc, price_date asc
                        """
                    ),
                    {
                        "from_ccy": fx_needed,
                        "to_ccy": portfolio.base_currency,
                        "max_trade_day": max_trade_day,
                    },
                ).mappings().all()

        return _compute_cash_balance_base(
            base_currency=portfolio.base_currency,
            opening_cash_balance=portfolio.cash_balance,
            rows=[dict(row) for row in tx_rows],
            fx_rows=[dict(row) for row in fx_rows],
        )

    def get_cash_flow_timeline(self, portfolio_id: int, user_id: str) -> CashFlowTimelineResponse:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")

            rows = conn.execute(
                text(
                    """
                    select trade_at::date as trade_date,
                           side,
                           sum(quantity * price)::float8 as total
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
        preview_data: list[dict],
    ) -> int:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")
            row = conn.execute(
                text(
                    """
                    insert into csv_import_batches (portfolio_id, owner_user_id, original_filename, total_rows, valid_rows, error_rows, preview_data)
                    values (:portfolio_id, :user_id, :filename, :total_rows, :valid_rows, :error_rows, cast(:preview_data as jsonb))
                    returning id
                    """
                ),
                {
                    "portfolio_id": portfolio_id,
                    "user_id": user_id,
                    "filename": filename,
                    "total_rows": total_rows,
                    "valid_rows": valid_rows,
                    "error_rows": error_rows,
                    "preview_data": json.dumps(preview_data),
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
        return dict(row)

    def commit_csv_import_batch(self, batch_id: int, user_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    update csv_import_batches
                    set status = 'committed', committed_at = now()
                    where id = :batch_id and owner_user_id = :user_id and status = 'pending'
                    """
                ),
                {"batch_id": batch_id, "user_id": user_id},
            )

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
