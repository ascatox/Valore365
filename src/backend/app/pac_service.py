import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class PacExecutionService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def process_due_rules(self) -> dict[str, int]:
        """Generate pending executions for all active PAC rules that are due today or before."""
        today = date.today()
        generated_total = 0
        rules_processed = 0

        with self.engine.begin() as conn:
            rules = conn.execute(
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

        for rule in rules:
            rule_id = int(rule["id"])
            try:
                from .repository import PortfolioRepository
                # Use a lightweight approach - just generate executions directly
                with self.engine.begin() as conn:
                    existing = conn.execute(
                        text("select scheduled_date from pac_executions where pac_rule_id = :rule_id"),
                        {"rule_id": rule_id},
                    ).mappings().all()
                    existing_dates = {r["scheduled_date"] for r in existing}

                    freq = str(rule["frequency"])
                    start = rule["start_date"]
                    end = rule["end_date"] or today
                    if end > today:
                        end = today

                    from datetime import timedelta
                    cursor = start
                    new_count = 0
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

                    generated_total += new_count
                    rules_processed += 1

            except Exception as exc:
                logger.exception("Error processing PAC rule %s: %s", rule_id, exc)

        logger.info("PAC processing complete: rules=%d, executions_generated=%d", rules_processed, generated_total)
        return {"rules_processed": rules_processed, "executions_generated": generated_total}
