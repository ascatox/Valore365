"""Scope multi-portafoglio per la vista aggregata.

Una vista aggregata guarda più portafogli dello stesso utente come se fossero
uno solo, senza creare un portafoglio nuovo. Ogni lettura aggregata passa da
qui per normalizzare gli id e verificare proprietà e valuta base, così route,
servizi e repository rifiutano gli stessi casi con gli stessi messaggi:

- lista vuota -> "Seleziona almeno un portafoglio" (400)
- portafoglio non dell'utente -> "Portfolio non trovato" (404)
- valute base diverse -> messaggio con "valuta base" (400)
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import text

from ._base import PortfolioData

EMPTY_SCOPE_MESSAGE = "Seleziona almeno un portafoglio"
NOT_FOUND_MESSAGE = "Portfolio non trovato"
MIXED_CURRENCY_MESSAGE = "I portafogli aggregati devono avere la stessa valuta base"


def normalize_portfolio_ids(portfolio_ids: Iterable[int]) -> list[int]:
    """Drop non-positive ids and duplicates, keeping the caller's order."""
    normalized: list[int] = []
    for portfolio_id in portfolio_ids:
        portfolio_id = int(portfolio_id)
        if portfolio_id <= 0 or portfolio_id in normalized:
            continue
        normalized.append(portfolio_id)
    return normalized


@dataclass(frozen=True)
class PortfolioScope:
    """A validated set of portfolios read as one."""

    portfolio_ids: tuple[int, ...]
    base_currency: str

    @property
    def is_aggregate(self) -> bool:
        return len(self.portfolio_ids) > 1

    @property
    def cache_key(self) -> tuple[int, ...]:
        return tuple(sorted(self.portfolio_ids))


def load_scope_portfolios(repo, conn, portfolio_ids: Iterable[int], user_id: str) -> tuple[list[int], list[PortfolioData]]:
    """Load and validate every portfolio of a scope on an open connection.

    Returns (normalized ids, portfolios) in the same order. Raises ValueError
    for an empty scope, a portfolio the user does not own, or portfolios with
    different base currencies. A one-portfolio scope goes through
    _get_portfolio_for_user exactly like the single-id methods.
    """
    ids = normalize_portfolio_ids(portfolio_ids)
    if not ids:
        raise ValueError(EMPTY_SCOPE_MESSAGE)

    if len(ids) == 1:
        portfolio = repo._get_portfolio_for_user(conn, ids[0], user_id)
        if portfolio is None:
            raise ValueError(NOT_FOUND_MESSAGE)
        return ids, [portfolio]

    rows = conn.execute(
        text(
            """
            select id, base_currency, cash_balance
            from portfolios
            where id = any(:portfolio_ids) and owner_user_id = :user_id
            """
        ),
        {"portfolio_ids": ids, "user_id": user_id},
    ).mappings().all()
    by_id = {
        int(r["id"]): PortfolioData(
            id=int(r["id"]),
            base_currency=str(r["base_currency"]),
            cash_balance=float(r["cash_balance"]),
        )
        for r in rows
    }
    if any(pid not in by_id for pid in ids):
        raise ValueError(NOT_FOUND_MESSAGE)
    portfolios = [by_id[pid] for pid in ids]
    if len({p.base_currency for p in portfolios}) != 1:
        raise ValueError(MIXED_CURRENCY_MESSAGE)
    return ids, portfolios


def row_portfolio_id(row, scope_ids: list[int]) -> int:
    """Portfolio a transaction row belongs to within a scope.

    A one-portfolio scope does not need to read the column, so rows shaped
    like the single-portfolio queries keep working.
    """
    if len(scope_ids) == 1:
        return scope_ids[0]
    return int(row["portfolio_id"])


class ScopeMixin:
    def resolve_portfolio_scope(self, portfolio_ids: Iterable[int], user_id: str) -> PortfolioScope:
        """Normalize and validate a list of portfolio ids for an aggregate read."""
        with self.engine.begin() as conn:
            ids, portfolios = load_scope_portfolios(self, conn, portfolio_ids, user_id)
        return PortfolioScope(
            portfolio_ids=tuple(ids),
            base_currency=portfolios[0].base_currency,
        )


def resolve_portfolio_scope(repo, portfolio_ids: Iterable[int], user_id: str) -> PortfolioScope:
    """Function form of PortfolioRepository.resolve_portfolio_scope."""
    return repo.resolve_portfolio_scope(portfolio_ids, user_id)
