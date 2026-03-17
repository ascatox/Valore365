from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import text

from ..models import (
    CashFlowEntry,
    TransactionCreate,
    TransactionListItem,
    TransactionRead,
    TransactionUpdate,
)


class TransactionsMixin:
    def create_transaction(self, payload: TransactionCreate, user_id: str) -> TransactionRead:
        side = payload.side.lower().strip()
        currency = payload.trade_currency.upper().strip()
        valid_sides = {"buy", "sell", "deposit", "withdrawal", "dividend", "fee", "interest"}
        if side not in valid_sides:
            raise ValueError(f"side deve essere uno tra: {', '.join(sorted(valid_sides))}")

        is_cash_movement = side in {"deposit", "withdrawal", "dividend", "fee", "interest"}

        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, payload.portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")

            if payload.asset_id is not None:
                if not self._asset_exists(conn, payload.asset_id):
                    raise ValueError("Asset non trovato")
                # Validate fraction support
                if side in {"buy", "sell"}:
                    asset_row = conn.execute(
                        text("select supports_fractions from assets where id = :id"),
                        {"id": payload.asset_id},
                    ).mappings().fetchone()
                    if asset_row and not asset_row["supports_fractions"]:
                        if payload.quantity != int(payload.quantity):
                            raise ValueError("Questo asset non supporta quote frazionate")
            elif not is_cash_movement:
                raise ValueError("asset_id obbligatorio per transazioni buy/sell")

            if side == "sell" and payload.asset_id is not None:
                self._assert_non_negative_inventory_timeline(
                    conn,
                    payload.portfolio_id,
                    payload.asset_id,
                    candidate={
                        "id": None,
                        "trade_at": payload.trade_at,
                        "side": side,
                        "quantity": float(payload.quantity),
                    },
                )

            row = conn.execute(
                text(
                    """
                    insert into transactions (
                        portfolio_id, asset_id, side, trade_at, quantity, price, fees, taxes, trade_currency, notes, owner_user_id
                    ) values (
                        :portfolio_id, :asset_id, :side, :trade_at, :quantity, :price, :fees, :taxes, :trade_currency, :notes, :owner_user_id
                    )
                    returning id
                    """
                ),
                {
                    "portfolio_id": payload.portfolio_id,
                    "asset_id": payload.asset_id,
                    "side": side,
                    "trade_at": payload.trade_at,
                    "quantity": payload.quantity,
                    "price": payload.price,
                    "fees": payload.fees,
                    "taxes": payload.taxes,
                    "trade_currency": currency,
                    "notes": payload.notes,
                    "owner_user_id": user_id,
                },
            ).fetchone()

        if row is None:
            raise ValueError("Impossibile creare la transazione")

        return TransactionRead(
            id=int(row.id),
            portfolio_id=payload.portfolio_id,
            asset_id=payload.asset_id,
            side=side,
            trade_at=payload.trade_at,
            quantity=payload.quantity,
            price=payload.price,
            fees=payload.fees,
            taxes=payload.taxes,
            trade_currency=currency,
            notes=payload.notes,
        )

    def list_transactions(self, portfolio_id: int, user_id: str) -> list[TransactionListItem]:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")

            rows = conn.execute(
                text(
                    """
                    select t.id,
                           t.portfolio_id,
                           t.asset_id,
                           t.side,
                           t.trade_at,
                           t.quantity::float8 as quantity,
                           t.price::float8 as price,
                           t.fees::float8 as fees,
                           t.taxes::float8 as taxes,
                           t.trade_currency,
                           t.notes,
                           a.symbol,
                           a.name as asset_name
                    from transactions t
                    left join assets a on a.id = t.asset_id
                    where t.portfolio_id = :portfolio_id
                    order by t.trade_at desc, t.id desc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

        return [
            TransactionListItem(
                id=int(row["id"]),
                portfolio_id=int(row["portfolio_id"]),
                asset_id=int(row["asset_id"]) if row["asset_id"] is not None else None,
                side=str(row["side"]),
                trade_at=row["trade_at"],
                quantity=float(row["quantity"]),
                price=float(row["price"]),
                fees=float(row["fees"]),
                taxes=float(row["taxes"]),
                trade_currency=str(row["trade_currency"]),
                notes=row["notes"],
                symbol=row["symbol"],
                asset_name=row["asset_name"],
            )
            for row in rows
        ]

    def get_portfolio_created_date(self, portfolio_id: int, user_id: str) -> date:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select created_at::date as created_date
                    from portfolios
                    where id = :portfolio_id and owner_user_id = :user_id
                    """
                ),
                {"portfolio_id": portfolio_id, "user_id": user_id},
            ).mappings().fetchone()
        if row is None or row["created_date"] is None:
            raise ValueError("Portfolio non trovato")
        return row["created_date"]

    def get_transactions_in_range(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[TransactionRead]:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")

            rows = conn.execute(
                text(
                    """
                    select t.id,
                           t.portfolio_id,
                           t.asset_id,
                           t.side,
                           t.trade_at,
                           t.quantity::float8 as quantity,
                           t.price::float8 as price,
                           t.fees::float8 as fees,
                           t.taxes::float8 as taxes,
                           t.trade_currency,
                           t.notes
                    from transactions t
                    where t.portfolio_id = :portfolio_id
                      and (:start_date is null or t.trade_at::date >= :start_date)
                      and (:end_date is null or t.trade_at::date <= :end_date)
                    order by t.trade_at asc, t.id asc
                    """
                ),
                {"portfolio_id": portfolio_id, "start_date": start_date, "end_date": end_date},
            ).mappings().all()

        return [
            TransactionRead(
                id=int(row["id"]),
                portfolio_id=int(row["portfolio_id"]),
                asset_id=int(row["asset_id"]) if row["asset_id"] is not None else None,
                side=str(row["side"]),
                trade_at=row["trade_at"],
                quantity=float(row["quantity"]),
                price=float(row["price"]),
                fees=float(row["fees"]),
                taxes=float(row["taxes"]),
                trade_currency=str(row["trade_currency"]),
                notes=row["notes"],
            )
            for row in rows
        ]

    def get_external_cashflows(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        include_trades: bool = False,
    ) -> list[CashFlowEntry]:
        txs = self.get_transactions_in_range(portfolio_id, user_id, start_date=start_date, end_date=end_date)
        external_sides = {"deposit", "withdrawal", "dividend", "fee", "interest"}
        if include_trades:
            external_sides |= {"buy", "sell"}
        selected = [tx for tx in txs if tx.side in external_sides]
        if not selected:
            return []

        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")

            base_ccy = portfolio.base_currency
            max_day = max(tx.trade_at.date() for tx in selected)
            currencies = sorted({tx.trade_currency for tx in selected if tx.trade_currency != base_ccy})
            fx_rows = []
            if currencies:
                fx_rows = conn.execute(
                    text(
                        """
                        select from_ccy, price_date, rate::float8 as rate
                        from fx_rates_1d
                        where from_ccy = any(:from_ccy)
                          and to_ccy = :to_ccy
                          and price_date <= :max_day
                        order by from_ccy asc, price_date asc
                        """
                    ),
                    {"from_ccy": currencies, "to_ccy": base_ccy, "max_day": max_day},
                ).mappings().all()

        fx_series: dict[str, list[tuple[date, float]]] = defaultdict(list)
        for row in fx_rows:
            fx_series[str(row["from_ccy"])].append((row["price_date"], float(row["rate"])))
        fx_dates = {ccy: [d for d, _ in points] for ccy, points in fx_series.items()}

        def fx_rate_on_or_before(currency: str, day: date) -> float:
            if currency == base_ccy:
                return 1.0
            series = fx_series.get(currency)
            dates = fx_dates.get(currency)
            if not series or not dates:
                return 1.0
            idx = bisect_right(dates, day) - 1
            if idx < 0:
                return 1.0
            return series[idx][1]

        out: list[CashFlowEntry] = []
        for tx in selected:
            amount = tx.quantity * tx.price
            fx = fx_rate_on_or_before(tx.trade_currency, tx.trade_at.date())
            amount_base = amount * fx
            costs_base = (tx.fees + tx.taxes) * fx

            if tx.side == "buy":
                # Investor outflow: price + fees/taxes (same sign as deposit)
                signed = amount_base + costs_base
            elif tx.side == "sell":
                # Investor inflow: price - fees/taxes (same sign as withdrawal)
                signed = -(amount_base - costs_base)
            elif tx.side in {"deposit", "dividend", "interest"}:
                signed = amount_base
            else:  # withdrawal, fee
                signed = -amount_base

            out.append(
                CashFlowEntry(
                    date=tx.trade_at.date().isoformat(),
                    side=tx.side,
                    amount=round(signed, 8),
                )
            )
        return out

    def get_portfolio_value_at_date(self, portfolio_id: int, user_id: str, target_date: date) -> float:
        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")
            base_ccy = portfolio.base_currency

            tx_rows = conn.execute(
                text(
                    """
                    select asset_id,
                           side,
                           trade_at::date as trade_date,
                           quantity::float8 as quantity,
                           price::float8 as price,
                           fees::float8 as fees,
                           taxes::float8 as taxes,
                           trade_currency
                    from transactions
                    where portfolio_id = :portfolio_id
                      and trade_at::date <= :target_date
                    order by trade_at asc, id asc
                    """
                ),
                {"portfolio_id": portfolio_id, "target_date": target_date},
            ).mappings().all()

            if not tx_rows:
                if target_date >= date.today():
                    return round(float(portfolio.cash_balance), 2)
                return 0.0

            asset_ids = sorted({int(r["asset_id"]) for r in tx_rows if r["asset_id"] is not None})
            asset_meta = self._get_asset_meta(conn, asset_ids) if asset_ids else {}

            price_rows = []
            if asset_ids:
                price_rows = conn.execute(
                    text(
                        """
                        select asset_id, price_date, close::float8 as close
                        from price_bars_1d
                        where asset_id = any(:asset_ids)
                          and price_date <= :target_date
                        order by asset_id asc, price_date asc
                        """
                    ),
                    {"asset_ids": asset_ids, "target_date": target_date},
                ).mappings().all()

            fx_needed = sorted(
                {
                    str(r["trade_currency"])
                    for r in tx_rows
                    if r["trade_currency"] is not None and str(r["trade_currency"]) != base_ccy
                }
                | {
                    meta.quote_currency
                    for meta in asset_meta.values()
                    if meta.quote_currency != base_ccy
                }
            )
            fx_rows = []
            if fx_needed:
                fx_rows = conn.execute(
                    text(
                        """
                        select from_ccy, price_date, rate::float8 as rate
                        from fx_rates_1d
                        where from_ccy = any(:from_ccy)
                          and to_ccy = :to_ccy
                          and price_date <= :target_date
                        order by from_ccy asc, price_date asc
                        """
                    ),
                    {"from_ccy": fx_needed, "to_ccy": base_ccy, "target_date": target_date},
                ).mappings().all()

        fx_series: dict[str, list[tuple[date, float]]] = defaultdict(list)
        for row in fx_rows:
            fx_series[str(row["from_ccy"])].append((row["price_date"], float(row["rate"])))
        fx_dates = {ccy: [d for d, _ in series] for ccy, series in fx_series.items()}

        def fx_rate_on_or_before(currency: str, day: date | None) -> float:
            if currency == base_ccy:
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

        holdings: dict[int, float] = defaultdict(float)
        cash_balance = 0.0

        for row in tx_rows:
            side = str(row["side"])
            qty = float(row["quantity"])
            price = float(row["price"])
            fees = float(row["fees"])
            taxes = float(row["taxes"])
            trade_day = row["trade_date"]
            trade_ccy = str(row["trade_currency"])
            fx = fx_rate_on_or_before(trade_ccy, trade_day)
            amount_base = qty * price * fx
            costs_base = (fees + taxes) * fx

            if side == "buy":
                aid = row["asset_id"]
                if aid is None:
                    continue
                holdings[int(aid)] += qty
                cash_balance -= amount_base + costs_base
            elif side == "sell":
                aid = row["asset_id"]
                if aid is None:
                    continue
                holdings[int(aid)] = max(0.0, holdings[int(aid)] - qty)
                cash_balance += amount_base - costs_base
            elif side in {"deposit", "dividend", "interest"}:
                cash_balance += amount_base
            elif side in {"withdrawal", "fee"}:
                cash_balance -= amount_base + costs_base

        price_series: dict[int, list[tuple[date, float]]] = defaultdict(list)
        for row in price_rows:
            aid = int(row["asset_id"])
            px = float(row["close"])
            if px > 0:
                price_series[aid].append((row["price_date"], px))
        price_dates = {aid: [d for d, _ in series] for aid, series in price_series.items()}

        total_assets_value = 0.0
        for aid, qty in holdings.items():
            if qty <= 0:
                continue
            series = price_series.get(aid)
            dates = price_dates.get(aid)
            if not series or not dates:
                continue
            idx = bisect_right(dates, target_date) - 1
            if idx < 0:
                continue
            px_day, px = series[idx]
            meta = asset_meta.get(aid)
            if meta is None:
                continue
            fx = fx_rate_on_or_before(meta.quote_currency, px_day)
            total_assets_value += qty * px * fx

        return round(cash_balance + total_assets_value, 2)

    def update_transaction(self, transaction_id: int, payload: TransactionUpdate, user_id: str) -> TransactionRead:
        updates = payload.model_dump(exclude_unset=True)
        with self.engine.begin() as conn:
            existing = self._get_transaction_for_user(conn, transaction_id, user_id)
            if existing is None:
                raise ValueError("Transazione non trovata")

            if "trade_at" in updates or "quantity" in updates:
                candidate_trade_at = updates.get("trade_at", existing["trade_at"])
                if candidate_trade_at is None:
                    raise ValueError("trade_at non puo essere nullo")
                self._assert_non_negative_inventory_timeline(
                    conn,
                    int(existing["portfolio_id"]),
                    int(existing["asset_id"]),
                    candidate={
                        "id": int(existing["id"]),
                        "trade_at": candidate_trade_at,
                        "side": str(existing["side"]),
                        "quantity": float(updates.get("quantity", existing["quantity"])),
                    },
                    exclude_transaction_id=transaction_id,
                )

            if updates:
                assignments = ", ".join(f"{field} = :{field}" for field in updates.keys())
                conn.execute(
                    text(f"update transactions set {assignments} where id = :transaction_id and owner_user_id = :user_id"),
                    {"transaction_id": transaction_id, "user_id": user_id, **updates},
                )
                existing = self._get_transaction_for_user(conn, transaction_id, user_id)
                if existing is None:
                    raise ValueError("Transazione non trovata")

        return TransactionRead(
            id=int(existing["id"]),
            portfolio_id=int(existing["portfolio_id"]),
            asset_id=int(existing["asset_id"]),
            side=str(existing["side"]),
            trade_at=existing["trade_at"],
            quantity=float(existing["quantity"]),
            price=float(existing["price"]),
            fees=float(existing["fees"]),
            taxes=float(existing["taxes"]),
            trade_currency=str(existing["trade_currency"]),
            notes=existing["notes"],
        )

    def delete_transaction(self, transaction_id: int, user_id: str) -> None:
        with self.engine.begin() as conn:
            existing = self._get_transaction_for_user(conn, transaction_id, user_id)
            if existing is None:
                raise ValueError("Transazione non trovata")
            self._assert_non_negative_inventory_timeline(
                conn,
                int(existing["portfolio_id"]),
                int(existing["asset_id"]),
                exclude_transaction_id=transaction_id,
            )
            deleted = conn.execute(
                text("delete from transactions where id = :transaction_id and owner_user_id = :user_id"),
                {"transaction_id": transaction_id, "user_id": user_id},
            )
            if deleted.rowcount == 0:
                raise ValueError("Transazione non trovata")
