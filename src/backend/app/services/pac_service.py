import logging
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..models import TransactionCreate
from ..repository import PortfolioRepository

logger = logging.getLogger(__name__)


class PacExecutionService:
    def __init__(self, engine: Engine, repo: PortfolioRepository | None = None) -> None:
        self.engine = engine
        self.repo = repo or PortfolioRepository(engine)

    def process_due_rules(self) -> dict[str, int]:
        """Generate due executions and auto-execute eligible PAC rules."""
        today = date.today()
        generated_total = 0
        rules_processed = 0
        auto_executed_total = 0
        failed_total = 0

        for rule in self._load_active_rules(today):
            rule_id = int(rule["id"])
            try:
                generated_total += self._generate_pending_executions_for_rule(rule, today)
                rules_processed += 1
            except Exception as exc:
                logger.exception("Error processing PAC rule %s: %s", rule_id, exc)

        for execution in self._list_due_auto_executions(today):
            execution_id = int(execution["id"])
            try:
                self._auto_execute_pending_execution(execution)
                auto_executed_total += 1
            except Exception as exc:
                logger.exception("Error auto-executing PAC execution %s: %s", execution_id, exc)
                try:
                    self.repo.fail_pac_execution(execution_id, str(exc), str(execution["owner_user_id"]))
                except Exception:
                    logger.exception("Error marking PAC execution %s as failed", execution_id)
                failed_total += 1

        logger.info(
            "PAC processing complete: rules=%d, executions_generated=%d, auto_executed=%d, failed=%d",
            rules_processed,
            generated_total,
            auto_executed_total,
            failed_total,
        )
        return {
            "rules_processed": rules_processed,
            "executions_generated": generated_total,
            "auto_executed": auto_executed_total,
            "failed": failed_total,
        }

    def _load_active_rules(self, today: date) -> list[dict]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select id, frequency, day_of_month, day_of_week, start_date, end_date
                    from pac_rules
                    where active = true
                      and start_date <= :today
                      and (end_date is null or end_date >= :today)
                    """
                ),
                {"today": today},
            ).mappings().all()
        return [dict(row) for row in rows]

    def _generate_pending_executions_for_rule(self, rule: dict, today: date) -> int:
        rule_id = int(rule["id"])
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("select scheduled_date from pac_executions where pac_rule_id = :rule_id"),
                {"rule_id": rule_id},
            ).mappings().all()
            existing_dates = {row["scheduled_date"] for row in existing}

            freq = str(rule["frequency"])
            start = rule["start_date"]
            end = rule["end_date"] or today
            if end > today:
                end = today

            cursor = start
            new_count = 0
            while cursor <= end:
                should_add = False
                if freq == "monthly" and rule["day_of_month"] is not None:
                    should_add = cursor.day == int(rule["day_of_month"])
                elif freq == "weekly" and rule["day_of_week"] is not None:
                    should_add = cursor.weekday() == int(rule["day_of_week"])
                elif freq == "biweekly" and rule["day_of_week"] is not None:
                    if cursor.weekday() == int(rule["day_of_week"]):
                        weeks_since_start = (cursor - start).days // 7
                        should_add = weeks_since_start % 2 == 0

                if should_add and cursor not in existing_dates:
                    conn.execute(
                        text(
                            """
                            insert into pac_executions (pac_rule_id, scheduled_date)
                            values (:rule_id, :scheduled_date)
                            on conflict (pac_rule_id, scheduled_date) do nothing
                            """
                        ),
                        {"rule_id": rule_id, "scheduled_date": cursor},
                    )
                    new_count += 1

                cursor += timedelta(days=1)

        return new_count

    def _list_due_auto_executions(self, today: date) -> list[dict]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select e.id,
                           e.pac_rule_id,
                           e.scheduled_date,
                           r.portfolio_id,
                           r.asset_id,
                           r.mode,
                           r.amount::float8 as amount,
                           r.quantity::float8 as quantity,
                           r.owner_user_id,
                           a.quote_currency
                    from pac_executions e
                    join pac_rules r on r.id = e.pac_rule_id
                    join assets a on a.id = r.asset_id
                    where e.status = 'pending'
                      and e.scheduled_date <= :today
                      and r.active = true
                      and r.auto_execute = true
                    order by e.scheduled_date asc, e.id asc
                    """
                ),
                {"today": today},
            ).mappings().all()
        return [dict(row) for row in rows]

    def _auto_execute_pending_execution(self, execution: dict) -> None:
        execution_id = int(execution["id"])
        portfolio_id = int(execution["portfolio_id"])
        asset_id = int(execution["asset_id"])
        user_id = str(execution["owner_user_id"])
        scheduled_date = execution["scheduled_date"]
        trade_currency = str(execution["quote_currency"])

        price = self._get_latest_price(asset_id, scheduled_date)
        mode = str(execution["mode"])
        if mode == "amount":
            amount = float(execution["amount"] or 0.0)
            quantity = amount / price if price > 0 else 0.0
        else:
            quantity = float(execution["quantity"] or 0.0)

        quantity = round(quantity, 8)
        if quantity <= 0:
            raise ValueError("Quantita calcolata non valida per auto-esecuzione PAC")

        trade_amount = quantity * price
        self._assert_sufficient_cash(
            portfolio_id=portfolio_id,
            user_id=user_id,
            trade_currency=trade_currency,
            scheduled_date=scheduled_date,
            trade_amount=trade_amount,
        )

        transaction = self.repo.create_transaction(
            TransactionCreate(
                portfolio_id=portfolio_id,
                asset_id=asset_id,
                side="buy",
                trade_at=datetime.combine(scheduled_date, datetime.min.time()),
                quantity=quantity,
                price=price,
                fees=0.0,
                taxes=0.0,
                trade_currency=trade_currency,
                notes=f"PAC auto execution #{execution_id}",
            ),
            user_id,
        )
        self.repo.confirm_pac_execution(execution_id, transaction.id, price, quantity, user_id)

    def _assert_sufficient_cash(
        self,
        *,
        portfolio_id: int,
        user_id: str,
        trade_currency: str,
        scheduled_date: date,
        trade_amount: float,
    ) -> None:
        base_currency = self.repo.get_portfolio_base_currency(portfolio_id, user_id)
        fx_rate = self._get_fx_rate_on_or_before(trade_currency, base_currency, scheduled_date)
        required_cash_base = trade_amount * fx_rate
        available_cash_base = self.repo.get_current_cash_balance_value(portfolio_id, user_id)
        if required_cash_base > available_cash_base + 1e-8:
            raise ValueError(
                f"Liquidita insufficiente per auto-esecuzione PAC: richiesti {required_cash_base:.2f} {base_currency}, "
                f"disponibili {available_cash_base:.2f} {base_currency}"
            )

    def _get_latest_price(self, asset_id: int, target_date: date) -> float:
        with self.engine.begin() as conn:
            tick_row = conn.execute(
                text(
                    """
                    select last::float8 as price
                    from price_ticks
                    where asset_id = :asset_id
                      and last is not null
                      and last > 0
                    order by ts desc
                    limit 1
                    """
                ),
                {"asset_id": asset_id},
            ).mappings().fetchone()
            if tick_row is not None:
                return float(tick_row["price"])

            bar_row = conn.execute(
                text(
                    """
                    select close::float8 as price
                    from price_bars_1d
                    where asset_id = :asset_id
                      and price_date <= :target_date
                      and close is not null
                      and close > 0
                    order by price_date desc
                    limit 1
                    """
                ),
                {"asset_id": asset_id, "target_date": target_date},
            ).mappings().fetchone()
            if bar_row is not None:
                return float(bar_row["price"])

        raise ValueError("Prezzo non disponibile per auto-esecuzione PAC")

    def _get_fx_rate_on_or_before(self, from_currency: str, to_currency: str, target_date: date) -> float:
        if from_currency == to_currency:
            return 1.0

        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select rate::float8 as rate
                    from fx_rates_1d
                    where from_ccy = :from_ccy
                      and to_ccy = :to_ccy
                      and price_date <= :target_date
                    order by price_date desc
                    limit 1
                    """
                ),
                {
                    "from_ccy": from_currency,
                    "to_ccy": to_currency,
                    "target_date": target_date,
                },
            ).mappings().fetchone()
        if row is None:
            return 1.0
        return float(row["rate"])
