import json
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
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")

            # Compute total from all cash-impacting transactions
            rows = conn.execute(
                text(
                    """
                    select trade_currency,
                           coalesce(sum(case
                             when side in ('deposit', 'interest', 'sell', 'dividend') then quantity * price
                             when side in ('withdrawal', 'fee') then -quantity * price
                             when side = 'buy' then -quantity * price - fees - taxes
                             else 0
                           end), 0)::float8 as balance
                    from transactions
                    where portfolio_id = :portfolio_id
                    group by trade_currency
                    order by trade_currency
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

            breakdown = [
                CashCurrencyBreakdown(currency=str(r["trade_currency"]), balance=round(float(r["balance"]), 2))
                for r in rows
            ]
            total_cash = round(sum(b.balance for b in breakdown), 2)

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
