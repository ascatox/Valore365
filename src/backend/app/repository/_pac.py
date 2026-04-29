from datetime import date, timedelta

from sqlalchemy import text

from ..models import (
    PacExecutionRead,
    PacRuleCreate,
    PacRuleRead,
    PacRuleUpdate,
)


class PacMixin:
    def create_pac_rule(self, payload: PacRuleCreate, user_id: str) -> PacRuleRead:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, payload.portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")
            if not self._asset_exists(conn, payload.asset_id):
                raise ValueError("Asset non trovato")

            row = conn.execute(
                text(
                    """
                    insert into pac_rules (portfolio_id, asset_id, mode, amount, quantity, frequency,
                        day_of_month, day_of_week, start_date, end_date, auto_execute, owner_user_id)
                    values (:portfolio_id, :asset_id, :mode, :amount, :quantity, :frequency,
                        :day_of_month, :day_of_week, :start_date, :end_date, :auto_execute, :owner_user_id)
                    returning id, created_at, updated_at
                    """
                ),
                {
                    "portfolio_id": payload.portfolio_id,
                    "asset_id": payload.asset_id,
                    "mode": payload.mode,
                    "amount": payload.amount,
                    "quantity": payload.quantity,
                    "frequency": payload.frequency,
                    "day_of_month": payload.day_of_month,
                    "day_of_week": payload.day_of_week,
                    "start_date": payload.start_date,
                    "end_date": payload.end_date,
                    "auto_execute": payload.auto_execute,
                    "owner_user_id": user_id,
                },
            ).mappings().fetchone()

        if row is None:
            raise ValueError("Impossibile creare regola PAC")
        return self.get_pac_rule(int(row["id"]), user_id)

    def get_pac_rule(self, rule_id: int, user_id: str) -> PacRuleRead:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select r.id, r.portfolio_id, r.asset_id, r.mode,
                           r.amount::float8, r.quantity::float8,
                           r.frequency, r.day_of_month, r.day_of_week,
                           r.start_date, r.end_date, r.auto_execute, r.active,
                           r.created_at, r.updated_at,
                           a.symbol, a.name as asset_name
                    from pac_rules r
                    join assets a on a.id = r.asset_id
                    where r.id = :rule_id and r.owner_user_id = :user_id
                    """
                ),
                {"rule_id": rule_id, "user_id": user_id},
            ).mappings().fetchone()
        if row is None:
            raise ValueError("Regola PAC non trovata")
        return PacRuleRead(
            id=int(row["id"]),
            portfolio_id=int(row["portfolio_id"]),
            asset_id=int(row["asset_id"]),
            symbol=row["symbol"],
            asset_name=row["asset_name"],
            mode=str(row["mode"]),
            amount=float(row["amount"]) if row["amount"] is not None else None,
            quantity=float(row["quantity"]) if row["quantity"] is not None else None,
            frequency=str(row["frequency"]),
            day_of_month=int(row["day_of_month"]) if row["day_of_month"] is not None else None,
            day_of_week=int(row["day_of_week"]) if row["day_of_week"] is not None else None,
            start_date=row["start_date"],
            end_date=row["end_date"],
            auto_execute=bool(row["auto_execute"]),
            active=bool(row["active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_pac_rules(self, portfolio_id: int, user_id: str) -> list[PacRuleRead]:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")
            rows = conn.execute(
                text(
                    """
                    select r.id, r.portfolio_id, r.asset_id, r.mode,
                           r.amount::float8, r.quantity::float8,
                           r.frequency, r.day_of_month, r.day_of_week,
                           r.start_date, r.end_date, r.auto_execute, r.active,
                           r.created_at, r.updated_at,
                           a.symbol, a.name as asset_name
                    from pac_rules r
                    join assets a on a.id = r.asset_id
                    where r.portfolio_id = :portfolio_id and r.owner_user_id = :user_id
                    order by r.active desc, r.created_at desc
                    """
                ),
                {"portfolio_id": portfolio_id, "user_id": user_id},
            ).mappings().all()

        return [
            PacRuleRead(
                id=int(r["id"]),
                portfolio_id=int(r["portfolio_id"]),
                asset_id=int(r["asset_id"]),
                symbol=r["symbol"],
                asset_name=r["asset_name"],
                mode=str(r["mode"]),
                amount=float(r["amount"]) if r["amount"] is not None else None,
                quantity=float(r["quantity"]) if r["quantity"] is not None else None,
                frequency=str(r["frequency"]),
                day_of_month=int(r["day_of_month"]) if r["day_of_month"] is not None else None,
                day_of_week=int(r["day_of_week"]) if r["day_of_week"] is not None else None,
                start_date=r["start_date"],
                end_date=r["end_date"],
                auto_execute=bool(r["auto_execute"]),
                active=bool(r["active"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def update_pac_rule(self, rule_id: int, payload: PacRuleUpdate, user_id: str) -> PacRuleRead:
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            raise ValueError("Nessun campo da aggiornare")

        set_clauses = ["updated_at = now()"]
        params: dict[str, object] = {"rule_id": rule_id, "user_id": user_id}
        for field, value in updates.items():
            params[field] = value
            set_clauses.append(f"{field} = :{field}")

        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    f"""
                    update pac_rules
                    set {", ".join(set_clauses)}
                    where id = :rule_id and owner_user_id = :user_id
                    returning id
                    """
                ),
                params,
            ).fetchone()
        if result is None:
            raise ValueError("Regola PAC non trovata")
        return self.get_pac_rule(rule_id, user_id)

    def delete_pac_rule(self, rule_id: int, user_id: str) -> None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("delete from pac_rules where id = :rule_id and owner_user_id = :user_id returning id"),
                {"rule_id": rule_id, "user_id": user_id},
            ).fetchone()
        if result is None:
            raise ValueError("Regola PAC non trovata")

    def list_pac_executions(self, rule_id: int, user_id: str) -> list[PacExecutionRead]:
        with self.engine.begin() as conn:
            # Verify ownership
            rule = conn.execute(
                text("select id from pac_rules where id = :rule_id and owner_user_id = :user_id"),
                {"rule_id": rule_id, "user_id": user_id},
            ).fetchone()
            if rule is None:
                raise ValueError("Regola PAC non trovata")

            rows = conn.execute(
                text(
                    """
                    select id, pac_rule_id, scheduled_date, status, transaction_id,
                           executed_price::float8, executed_quantity::float8,
                           error_message, created_at, executed_at
                    from pac_executions
                    where pac_rule_id = :rule_id
                    order by scheduled_date desc
                    """
                ),
                {"rule_id": rule_id},
            ).mappings().all()

        return [
            PacExecutionRead(
                id=int(r["id"]),
                pac_rule_id=int(r["pac_rule_id"]),
                scheduled_date=r["scheduled_date"],
                status=str(r["status"]),
                transaction_id=int(r["transaction_id"]) if r["transaction_id"] is not None else None,
                executed_price=float(r["executed_price"]) if r["executed_price"] is not None else None,
                executed_quantity=float(r["executed_quantity"]) if r["executed_quantity"] is not None else None,
                error_message=r["error_message"],
                created_at=r["created_at"],
                executed_at=r["executed_at"],
            )
            for r in rows
        ]

    def list_pending_pac_executions(self, portfolio_id: int, user_id: str) -> list[PacExecutionRead]:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")

            rows = conn.execute(
                text(
                    """
                    select e.id, e.pac_rule_id, e.scheduled_date, e.status, e.transaction_id,
                           e.executed_price::float8, e.executed_quantity::float8,
                           e.error_message, e.created_at, e.executed_at
                    from pac_executions e
                    join pac_rules r on r.id = e.pac_rule_id
                    where r.portfolio_id = :portfolio_id
                      and r.owner_user_id = :user_id
                      and e.status = 'pending'
                    order by e.scheduled_date asc
                    """
                ),
                {"portfolio_id": portfolio_id, "user_id": user_id},
            ).mappings().all()

        return [
            PacExecutionRead(
                id=int(r["id"]),
                pac_rule_id=int(r["pac_rule_id"]),
                scheduled_date=r["scheduled_date"],
                status=str(r["status"]),
                transaction_id=int(r["transaction_id"]) if r["transaction_id"] is not None else None,
                executed_price=float(r["executed_price"]) if r["executed_price"] is not None else None,
                executed_quantity=float(r["executed_quantity"]) if r["executed_quantity"] is not None else None,
                error_message=r["error_message"],
                created_at=r["created_at"],
                executed_at=r["executed_at"],
            )
            for r in rows
        ]

    def confirm_pac_execution(self, execution_id: int, transaction_id: int, price: float, quantity: float, user_id: str) -> None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    update pac_executions
                    set status = 'executed', transaction_id = :transaction_id,
                        executed_price = :price, executed_quantity = :quantity,
                        executed_at = now()
                    where id = :execution_id and status = 'pending'
                      and pac_rule_id in (select id from pac_rules where owner_user_id = :user_id)
                    returning id
                    """
                ),
                {
                    "execution_id": execution_id,
                    "transaction_id": transaction_id,
                    "price": price,
                    "quantity": quantity,
                    "user_id": user_id,
                },
            ).fetchone()
        if result is None:
            raise ValueError("Esecuzione PAC non trovata o gia processata")

    def skip_pac_execution(self, execution_id: int, user_id: str) -> None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    update pac_executions
                    set status = 'skipped', executed_at = now()
                    where id = :execution_id and status = 'pending'
                      and pac_rule_id in (select id from pac_rules where owner_user_id = :user_id)
                    returning id
                    """
                ),
                {"execution_id": execution_id, "user_id": user_id},
            ).fetchone()
        if result is None:
            raise ValueError("Esecuzione PAC non trovata o gia processata")

    def generate_pending_executions(self, rule_id: int) -> int:
        """Generate pending executions for a PAC rule up to today. Returns count of new executions."""
        with self.engine.begin() as conn:
            rule = conn.execute(
                text(
                    """
                    select id, frequency, day_of_month, day_of_week, start_date, end_date, active
                    from pac_rules
                    where id = :rule_id
                    """
                ),
                {"rule_id": rule_id},
            ).mappings().fetchone()

            if rule is None or not rule["active"]:
                return 0

            today = date.today()
            start = rule["start_date"]
            end = rule["end_date"] or today
            if end > today:
                end = today

            existing = conn.execute(
                text("select scheduled_date from pac_executions where pac_rule_id = :rule_id"),
                {"rule_id": rule_id},
            ).mappings().all()
            existing_dates = {r["scheduled_date"] for r in existing}

            dates_to_create: list[date] = []
            freq = str(rule["frequency"])
            cursor = start
            while cursor <= end:
                should_add = False
                if freq == "monthly" and rule["day_of_month"] is not None:
                    if cursor.day == int(rule["day_of_month"]):
                        should_add = True
                elif freq == "weekly" and rule["day_of_week"] is not None:
                    if cursor.weekday() == int(rule["day_of_week"]):
                        should_add = True
                elif freq == "biweekly" and rule["day_of_week"] is not None:
                    if cursor.weekday() == int(rule["day_of_week"]):
                        weeks_since_start = (cursor - start).days // 7
                        if weeks_since_start % 2 == 0:
                            should_add = True

                if should_add and cursor not in existing_dates:
                    dates_to_create.append(cursor)

                cursor += timedelta(days=1)

            for d in dates_to_create:
                conn.execute(
                    text(
                        """
                        insert into pac_executions (pac_rule_id, scheduled_date)
                        values (:rule_id, :scheduled_date)
                        on conflict (pac_rule_id, scheduled_date) do nothing
                        """
                    ),
                    {"rule_id": rule_id, "scheduled_date": d},
                )

            return len(dates_to_create)
