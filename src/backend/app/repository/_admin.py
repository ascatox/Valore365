from sqlalchemy import text

from ..models import (
    AdminUsageSummary,
    UserSettingsRead,
    UserSettingsUpdate,
)


class AdminMixin:
    def record_public_instant_analyzer_event(
        self,
        *,
        client_ip_hash: str | None,
        input_mode: str,
        positions_count: int,
        success: bool,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into public_instant_analyzer_events (
                      client_ip_hash,
                      input_mode,
                      positions_count,
                      success,
                      created_at
                    )
                    values (
                      :client_ip_hash,
                      :input_mode,
                      :positions_count,
                      :success,
                      now()
                    )
                    """
                ),
                {
                    "client_ip_hash": client_ip_hash,
                    "input_mode": input_mode,
                    "positions_count": positions_count,
                    "success": success,
                },
            )

    def get_admin_usage_summary(self) -> AdminUsageSummary:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    with registered_users as (
                        select distinct user_id as uid
                        from app_users
                        where user_id <> 'dev-user'
                    )
                    select
                        (select count(*)::int from registered_users) as registered_users,
                        (select count(distinct owner_user_id)::int from portfolios where owner_user_id <> 'dev-user') as users_with_portfolios,
                        (select count(distinct owner_user_id)::int from transactions where owner_user_id <> 'dev-user') as users_with_transactions,
                        (select count(distinct owner_user_id)::int from csv_import_batches where owner_user_id <> 'dev-user') as users_with_imports,
                        (select count(*)::int from portfolios where owner_user_id <> 'dev-user') as portfolios_total,
                        (select count(*)::int from transactions where owner_user_id <> 'dev-user') as transactions_total,
                        (select count(*)::int from csv_import_batches where owner_user_id <> 'dev-user') as csv_import_batches_total,
                        (select count(*)::int from portfolios where owner_user_id <> 'dev-user' and created_at >= now() - interval '7 days') as portfolios_created_7d,
                        (select count(*)::int from csv_import_batches where owner_user_id <> 'dev-user' and created_at >= now() - interval '7 days') as imports_started_7d,
                        (select count(*)::int from public_instant_analyzer_events) as analyzer_runs_total,
                        (select count(*)::int from public_instant_analyzer_events where created_at >= now() - interval '7 days') as analyzer_runs_7d,
                        (select count(distinct client_ip_hash)::int from public_instant_analyzer_events where created_at >= now() - interval '7 days' and client_ip_hash is not null) as analyzer_unique_visitors_7d
                    """
                )
            ).mappings().one()

        return AdminUsageSummary(
            registered_users=int(row["registered_users"] or 0),
            users_with_portfolios=int(row["users_with_portfolios"] or 0),
            users_with_transactions=int(row["users_with_transactions"] or 0),
            users_with_imports=int(row["users_with_imports"] or 0),
            portfolios_total=int(row["portfolios_total"] or 0),
            transactions_total=int(row["transactions_total"] or 0),
            csv_import_batches_total=int(row["csv_import_batches_total"] or 0),
            portfolios_created_7d=int(row["portfolios_created_7d"] or 0),
            imports_started_7d=int(row["imports_started_7d"] or 0),
            analyzer_runs_total=int(row["analyzer_runs_total"] or 0),
            analyzer_runs_7d=int(row["analyzer_runs_7d"] or 0),
            analyzer_unique_visitors_7d=int(row["analyzer_unique_visitors_7d"] or 0),
            public_instant_analyzer_tracked=True,
        )

    def get_user_settings(self, user_id: str) -> UserSettingsRead:
        normalized_user_id = (user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id non valido")
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select user_id,
                           broker_default_fee::float8 as broker_default_fee,
                           copilot_provider,
                           copilot_model,
                           copilot_api_key_enc,
                           fire_annual_expenses::float8 as fire_annual_expenses,
                           fire_annual_contribution::float8 as fire_annual_contribution,
                           fire_expected_return_pct::float8 as fire_expected_return_pct,
                           fire_safe_withdrawal_rate::float8 as fire_safe_withdrawal_rate,
                           fire_capital_gains_tax_rate::float8 as fire_capital_gains_tax_rate,
                           fire_current_age,
                           fire_target_age
                    from app_user_settings
                    where user_id = :user_id
                    """
                ),
                {"user_id": normalized_user_id},
            ).mappings().fetchone()
        if row is None:
            return UserSettingsRead(user_id=normalized_user_id, broker_default_fee=0.0)
        return UserSettingsRead(
            user_id=str(row["user_id"]),
            broker_default_fee=float(row["broker_default_fee"] or 0.0),
            copilot_provider=str(row["copilot_provider"] or ""),
            copilot_model=str(row["copilot_model"] or ""),
            copilot_api_key_set=bool(row["copilot_api_key_enc"]),
            fire_annual_expenses=float(row["fire_annual_expenses"] or 0.0),
            fire_annual_contribution=float(row["fire_annual_contribution"] or 0.0),
            fire_expected_return_pct=float(row["fire_expected_return_pct"] or 5.0),
            fire_safe_withdrawal_rate=float(row["fire_safe_withdrawal_rate"] or 4.0),
            fire_capital_gains_tax_rate=float(row["fire_capital_gains_tax_rate"] or 26.0),
            fire_current_age=int(row["fire_current_age"]) if row["fire_current_age"] is not None else None,
            fire_target_age=int(row["fire_target_age"]) if row["fire_target_age"] is not None else None,
        )

    def get_user_copilot_api_key_enc(self, user_id: str) -> str:
        """Return the raw encrypted API key (or empty string)."""
        normalized_user_id = (user_id or "").strip()
        if not normalized_user_id:
            return ""
        with self.engine.begin() as conn:
            row = conn.execute(
                text("select copilot_api_key_enc from app_user_settings where user_id = :user_id"),
                {"user_id": normalized_user_id},
            ).mappings().fetchone()
        return str(row["copilot_api_key_enc"] or "") if row else ""

    def upsert_user_settings(self, user_id: str, payload: UserSettingsUpdate, api_key_enc: str | None = None) -> UserSettingsRead:
        normalized_user_id = (user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id non valido")
        fields_set = getattr(payload, "model_fields_set", set())

        # Build SET clauses dynamically — only update provided fields
        set_parts = ["updated_at = now()"]
        params: dict = {"user_id": normalized_user_id}

        if "broker_default_fee" in fields_set and payload.broker_default_fee is not None:
            set_parts.append("broker_default_fee = :broker_default_fee")
            params["broker_default_fee"] = payload.broker_default_fee
        if "copilot_provider" in fields_set and payload.copilot_provider is not None:
            set_parts.append("copilot_provider = :copilot_provider")
            params["copilot_provider"] = payload.copilot_provider
        if "copilot_model" in fields_set and payload.copilot_model is not None:
            set_parts.append("copilot_model = :copilot_model")
            params["copilot_model"] = payload.copilot_model
        if "fire_annual_expenses" in fields_set and payload.fire_annual_expenses is not None:
            set_parts.append("fire_annual_expenses = :fire_annual_expenses")
            params["fire_annual_expenses"] = payload.fire_annual_expenses
        if "fire_annual_contribution" in fields_set and payload.fire_annual_contribution is not None:
            set_parts.append("fire_annual_contribution = :fire_annual_contribution")
            params["fire_annual_contribution"] = payload.fire_annual_contribution
        if "fire_expected_return_pct" in fields_set and payload.fire_expected_return_pct is not None:
            set_parts.append("fire_expected_return_pct = :fire_expected_return_pct")
            params["fire_expected_return_pct"] = payload.fire_expected_return_pct
        if "fire_safe_withdrawal_rate" in fields_set and payload.fire_safe_withdrawal_rate is not None:
            set_parts.append("fire_safe_withdrawal_rate = :fire_safe_withdrawal_rate")
            params["fire_safe_withdrawal_rate"] = payload.fire_safe_withdrawal_rate
        if "fire_capital_gains_tax_rate" in fields_set and payload.fire_capital_gains_tax_rate is not None:
            set_parts.append("fire_capital_gains_tax_rate = :fire_capital_gains_tax_rate")
            params["fire_capital_gains_tax_rate"] = payload.fire_capital_gains_tax_rate
        if "fire_current_age" in fields_set:
            set_parts.append("fire_current_age = :fire_current_age")
            params["fire_current_age"] = payload.fire_current_age
        if "fire_target_age" in fields_set:
            set_parts.append("fire_target_age = :fire_target_age")
            params["fire_target_age"] = payload.fire_target_age
        if api_key_enc is not None:
            set_parts.append("copilot_api_key_enc = :copilot_api_key_enc")
            params["copilot_api_key_enc"] = api_key_enc

        set_clause = ", ".join(set_parts)

        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    insert into app_user_settings (
                      user_id,
                      broker_default_fee,
                      copilot_provider,
                      copilot_model,
                      copilot_api_key_enc,
                      fire_annual_expenses,
                      fire_annual_contribution,
                      fire_expected_return_pct,
                      fire_safe_withdrawal_rate,
                      fire_capital_gains_tax_rate,
                      fire_current_age,
                      fire_target_age,
                      updated_at
                    )
                    values (
                      :user_id,
                      coalesce(:bf, 0),
                      coalesce(:cp, ''),
                      coalesce(:cm, ''),
                      coalesce(:ck, ''),
                      coalesce(:fae, 0),
                      coalesce(:fac, 0),
                      coalesce(:ferp, 5),
                      coalesce(:fswr, 4),
                      coalesce(:fcgtr, 26),
                      :fca,
                      :fta,
                      now()
                    )
                    on conflict (user_id)
                    do update set {set_clause}
                    """
                ),
                {
                    **params,
                    "bf": payload.broker_default_fee,
                    "cp": payload.copilot_provider,
                    "cm": payload.copilot_model,
                    "ck": api_key_enc,
                    "fae": payload.fire_annual_expenses,
                    "fac": payload.fire_annual_contribution,
                    "ferp": payload.fire_expected_return_pct,
                    "fswr": payload.fire_safe_withdrawal_rate,
                    "fcgtr": payload.fire_capital_gains_tax_rate,
                    "fca": payload.fire_current_age,
                    "fta": payload.fire_target_age,
                },
            )
        return self.get_user_settings(normalized_user_id)
