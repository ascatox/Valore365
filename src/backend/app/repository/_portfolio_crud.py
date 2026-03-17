from sqlalchemy import text

from ..models import (
    PortfolioCloneRequest,
    PortfolioCloneResponse,
    PortfolioCreate,
    PortfolioRead,
    PortfolioUpdate,
)


class PortfolioCrudMixin:
    def list_portfolios(self, user_id: str) -> list[PortfolioRead]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select id, name, base_currency, timezone, target_notional, cash_balance, created_at
                    from portfolios
                    where owner_user_id = :user_id
                    order by created_at desc, id desc
                    """
                ),
                {"user_id": user_id},
            ).mappings().all()

        current_cash_by_portfolio = {
            int(row["id"]): self.get_current_cash_balance_value(int(row["id"]), user_id)
            for row in rows
        }

        return [
            PortfolioRead(
                id=int(row["id"]),
                name=str(row["name"]),
                base_currency=str(row["base_currency"]),
                timezone=str(row["timezone"]),
                target_notional=float(row["target_notional"]) if row["target_notional"] is not None else None,
                cash_balance=float(row["cash_balance"]),
                created_at=row["created_at"],
                current_cash_balance=current_cash_by_portfolio.get(int(row["id"])),
            )
            for row in rows
        ]

    def create_portfolio(self, payload: PortfolioCreate, user_id: str) -> PortfolioRead:
        name = payload.name.strip()
        base_currency = payload.base_currency.strip().upper()
        timezone = payload.timezone.strip()
        target_notional = float(payload.target_notional) if payload.target_notional is not None else None
        cash_balance = float(payload.cash_balance)

        if not name:
            raise ValueError("Nome portfolio obbligatorio")
        if not timezone:
            raise ValueError("Timezone obbligatoria")

        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    insert into portfolios (name, base_currency, timezone, target_notional, cash_balance, owner_user_id)
                    values (:name, :base_currency, :timezone, :target_notional, :cash_balance, :owner_user_id)
                    returning id, name, base_currency, timezone, target_notional, cash_balance, created_at
                    """
                ),
                {
                    "name": name,
                    "base_currency": base_currency,
                    "timezone": timezone,
                    "target_notional": target_notional,
                    "cash_balance": cash_balance,
                    "owner_user_id": user_id,
                },
            ).mappings().fetchone()

        if row is None:
            raise ValueError("Impossibile creare portfolio")

        return PortfolioRead(
            id=int(row["id"]),
            name=str(row["name"]),
            base_currency=str(row["base_currency"]),
            timezone=str(row["timezone"]),
            target_notional=float(row["target_notional"]) if row["target_notional"] is not None else None,
            cash_balance=float(row["cash_balance"]),
            created_at=row["created_at"],
            current_cash_balance=float(row["cash_balance"]),
        )

    def update_portfolio(self, portfolio_id: int, payload: PortfolioUpdate, user_id: str) -> PortfolioRead:
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            raise ValueError("Nessun campo da aggiornare")

        set_clauses: list[str] = []
        params: dict[str, object] = {"id": portfolio_id, "user_id": user_id}

        if "name" in updates:
            name = str(updates["name"]).strip()
            if not name:
                raise ValueError("Nome portfolio obbligatorio")
            params["name"] = name
            set_clauses.append("name = :name")

        if "base_currency" in updates:
            base_currency = str(updates["base_currency"]).strip().upper()
            if len(base_currency) != 3:
                raise ValueError("Valuta base non valida")
            params["base_currency"] = base_currency
            set_clauses.append("base_currency = :base_currency")

        if "timezone" in updates:
            timezone = str(updates["timezone"]).strip()
            if not timezone:
                raise ValueError("Timezone obbligatoria")
            params["timezone"] = timezone
            set_clauses.append("timezone = :timezone")

        if "target_notional" in updates:
            raw_target_notional = updates["target_notional"]
            params["target_notional"] = None if raw_target_notional is None else float(raw_target_notional)
            set_clauses.append("target_notional = :target_notional")

        if "cash_balance" in updates:
            raw_cash_balance = updates["cash_balance"]
            if raw_cash_balance is None or float(raw_cash_balance) < 0:
                raise ValueError("Cash balance non valido")
            params["cash_balance"] = float(raw_cash_balance)
            set_clauses.append("cash_balance = :cash_balance")

        if not set_clauses:
            raise ValueError("Nessun campo valido da aggiornare")

        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    f"""
                    update portfolios
                    set {", ".join(set_clauses)}
                    where id = :id and owner_user_id = :user_id
                    returning id, name, base_currency, timezone, target_notional, cash_balance, created_at
                    """
                )
                ,
                params,
            ).mappings().fetchone()

        if row is None:
            raise ValueError("Portfolio non trovato")

        return PortfolioRead(
            id=int(row["id"]),
            name=str(row["name"]),
            base_currency=str(row["base_currency"]),
            timezone=str(row["timezone"]),
            target_notional=float(row["target_notional"]) if row["target_notional"] is not None else None,
            cash_balance=float(row["cash_balance"]),
            created_at=row["created_at"],
            current_cash_balance=self.get_current_cash_balance_value(portfolio_id, user_id),
        )

    def clone_portfolio(self, portfolio_id: int, payload: PortfolioCloneRequest, user_id: str) -> PortfolioCloneResponse:
        with self.engine.begin() as conn:
            source = conn.execute(
                text(
                    """
                    select id, name, base_currency, timezone, target_notional, cash_balance
                    from portfolios
                    where id = :id and owner_user_id = :user_id
                    """
                ),
                {"id": portfolio_id, "user_id": user_id},
            ).mappings().fetchone()
            if source is None:
                raise ValueError("Portfolio non trovato")

            clone_name = (payload.name or "").strip()
            if not clone_name:
                clone_name = f'{str(source["name"]).strip()} (Copia)'
            if not clone_name:
                raise ValueError("Nome portfolio clone obbligatorio")

            created = conn.execute(
                text(
                    """
                    insert into portfolios (name, base_currency, timezone, target_notional, cash_balance, owner_user_id)
                    values (:name, :base_currency, :timezone, :target_notional, :cash_balance, :owner_user_id)
                    returning id, name, base_currency, timezone, target_notional, cash_balance, created_at
                    """
                ),
                {
                    "name": clone_name,
                    "base_currency": str(source["base_currency"]),
                    "timezone": str(source["timezone"]),
                    "target_notional": source["target_notional"],
                    "cash_balance": float(source["cash_balance"] or 0),
                    "owner_user_id": user_id,
                },
            ).mappings().fetchone()
            if created is None:
                raise ValueError("Impossibile clonare portfolio")

            new_portfolio_id = int(created["id"])

            inserted_alloc = conn.execute(
                text(
                    """
                    insert into portfolio_target_allocations (portfolio_id, asset_id, weight_pct, owner_user_id)
                    select :new_portfolio_id, pta.asset_id, pta.weight_pct, cast(:new_owner_user_id as varchar(255))
                    from portfolio_target_allocations pta
                    where pta.portfolio_id = :source_portfolio_id
                      and pta.owner_user_id = :source_owner_user_id
                    """
                ),
                {
                    "new_portfolio_id": new_portfolio_id,
                    "source_portfolio_id": portfolio_id,
                    "source_owner_user_id": user_id,
                    "new_owner_user_id": user_id,
                },
            )

        return PortfolioCloneResponse(
            portfolio=PortfolioRead(
                id=int(created["id"]),
                name=str(created["name"]),
                base_currency=str(created["base_currency"]),
                timezone=str(created["timezone"]),
                target_notional=float(created["target_notional"]) if created["target_notional"] is not None else None,
                cash_balance=float(created["cash_balance"]),
                created_at=created["created_at"],
                current_cash_balance=float(created["cash_balance"]),
            ),
            target_allocations_copied=int(inserted_alloc.rowcount or 0),
        )

    def delete_portfolio(self, portfolio_id: int, user_id: str) -> None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("delete from portfolios where id = :id and owner_user_id = :user_id returning id"),
                {"id": portfolio_id, "user_id": user_id},
            ).fetchone()

        if row is None:
            raise ValueError("Portfolio non trovato")
