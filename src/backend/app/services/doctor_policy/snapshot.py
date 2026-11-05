"""Snapshot of the holdings a Doctor policy is evaluated on.

One snapshot = the positions of a scope at one instant, with the price
timestamps and the freshness of the data. Every metric of the policy is
computed once from it (``compute_metrics``) and every rule is evaluated on
those metrics: evaluation before/after a draft, and the Scenario Lab, compare
values computed on the same snapshot.

``build_snapshot`` reuses the existing loaders: the scope is validated as the
aggregate Doctor features do (``load_scope_portfolios`` /
``resolve_portfolio_scope``), positions come from ``get_positions`` (one
portfolio) or ``get_positions_multi`` (several, an asset held in more
portfolios is one position), holdings are built by
``portfolio_doctor._holdings`` and the freshness reads the same fields and
helpers as the MCP ``data_freshness`` block.

``snapshot_from_holdings`` is the pure constructor (tests, Scenario Lab).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import cached_property
from typing import Any

from ...mcp_server.freshness import _latest_price_value, _note, _sort_key, sync_status
from ..portfolio_doctor._holdings import (
    AnalyzedHolding,
    _holdings_from_positions,
    _merge_holdings_by_asset,
)
from .scope import normalize_scope_ids

SNAPSHOT_ID_LENGTH = 16


def is_cash_holding(holding: AnalyzedHolding) -> bool:
    """Cash positions (asset_type ``cash``): outside every policy denominator,
    like the cash balance (same rule as the X-Ray coverage denominator)."""
    return (holding.asset_type or "").strip().lower() == "cash"


def _iso(value: Any) -> str | None:
    key = _sort_key(value)
    if key is None:
        return None
    if isinstance(value, datetime):
        return key.isoformat()
    return value.isoformat()


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            try:
                value = date.fromisoformat(value)
            except ValueError:
                return None
    return _sort_key(value)


@dataclass
class DoctorSnapshot:
    portfolio_ids: list[int]
    holdings: list[AnalyzedHolding]
    base_currency: str | None = None
    # Cash balance of the portfolios + cash positions (not in any denominator).
    cash_value: float = 0.0
    # asset_id -> ISO timestamp of the latest price used (tick or daily close).
    price_as_of: dict[int, str | None] = field(default_factory=dict)
    # asset_ids flagged price_stale by the positions service (TASK-53).
    stale_asset_ids: set[int] = field(default_factory=set)
    # asset_ids without any market price (valued at cost or not at all).
    missing_price_asset_ids: set[int] = field(default_factory=set)
    last_successful_price_sync: str | None = None
    last_sync_status: str | None = None
    sync_available: bool = False
    freshness_note: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # -- derived values ---------------------------------------------------

    # A snapshot is read once and never mutated afterwards: the invested
    # holdings and their total are computed once (weight_of is called for every
    # holding by every metric; recomputing the total made it O(n^2), ~17 s on a
    # 20 x 300 assets scope).
    @cached_property
    def _invested(self) -> tuple[AnalyzedHolding, ...]:
        return tuple(h for h in self.holdings if not is_cash_holding(h) and _value_of(h) > 0)

    @property
    def invested_holdings(self) -> list[AnalyzedHolding]:
        """Non-cash holdings with a positive market value."""
        return list(self._invested)

    @cached_property
    def invested_value(self) -> float:
        """Market value of the invested holdings (cash excluded), base currency."""
        return sum(_value_of(h) for h in self._invested)

    @property
    def is_empty(self) -> bool:
        return self.invested_value <= 0

    def weight_of(self, holding: AnalyzedHolding) -> float:
        """Unrounded weight of a holding over the invested value (0-100)."""
        total = self.invested_value
        if total <= 0 or is_cash_holding(holding):
            return 0.0
        return max(0.0, _value_of(holding)) / total * 100.0

    @property
    def stale_symbols(self) -> list[str]:
        return sorted({h.symbol for h in self.invested_holdings if h.asset_id in self.stale_asset_ids})

    @property
    def missing_price_symbols(self) -> list[str]:
        return sorted({h.symbol for h in self.invested_holdings if h.asset_id in self.missing_price_asset_ids})

    @cached_property
    def quote_as_of(self) -> str | None:
        """Timestamp (ISO) of the oldest price used among the invested holdings."""
        oldest: tuple[datetime, str] | None = None
        for h in self.invested_holdings:
            raw = self.price_as_of.get(h.asset_id)
            parsed = _to_datetime(raw)
            if parsed is None or raw is None:
                continue
            if oldest is None or parsed < oldest[0]:
                oldest = (parsed, raw)
        return oldest[1] if oldest else None

    @property
    def sync_failed(self) -> bool:
        return self.last_sync_status == "failed"

    def price_age_days(self, holding: AnalyzedHolding, now: datetime) -> int | None:
        parsed = _to_datetime(self.price_as_of.get(holding.asset_id))
        if parsed is None:
            return None
        return (now.astimezone(UTC).date() - parsed.astimezone(UTC).date()).days

    @property
    def data_quality(self) -> dict[str, Any]:
        """Contract §4 ``data_quality`` block."""
        stale = self.stale_symbols
        missing = self.missing_price_symbols
        if stale or self.sync_failed:
            status = "stale"
        elif missing:
            status = "partial"
        elif not self.sync_available and not self.price_as_of:
            status = "unknown"
        else:
            status = "ok"
        return {
            "status": status,
            "last_successful_price_sync": self.last_successful_price_sync,
            "last_sync_status": self.last_sync_status,
            "stale_symbols": stale,
            "missing_price_symbols": missing,
            "oldest_price_at": self.quote_as_of,
            "note": self.freshness_note,
        }

    @cached_property
    def snapshot_id(self) -> str:
        """Short sha256 over positions, prices and classification inputs."""
        rows = []
        for h in sorted(self.holdings, key=lambda x: (x.asset_id, x.symbol)):
            rows.append([
                h.asset_id,
                round(float(h.market_value), 6),
                round(self.weight_of(h), 6),
                h.symbol, h.name, h.asset_type, h.quote_currency, h.isin,
                h.investment_focus, h.index_tracked, h.category, h.enrichment_name,
                self.price_as_of.get(h.asset_id),
                h.asset_id in self.stale_asset_ids,
                h.asset_id in self.missing_price_asset_ids,
            ])
        payload = {
            "portfolio_ids": sorted(self.portfolio_ids),
            "base_currency": self.base_currency,
            "cash_value": round(float(self.cash_value), 6),
            "holdings": rows,
            "last_sync_status": self.last_sync_status,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:SNAPSHOT_ID_LENGTH]


def _value_of(holding: AnalyzedHolding) -> float:
    return max(0.0, float(holding.market_value or 0.0))


def snapshot_from_holdings(
    holdings: Sequence[AnalyzedHolding],
    *,
    portfolio_ids: Iterable[int] = (),
    base_currency: str | None = None,
    cash_value: float = 0.0,
    price_as_of: Mapping[int, Any] | None = None,
    stale_asset_ids: Iterable[int] = (),
    missing_price_asset_ids: Iterable[int] = (),
    last_successful_price_sync: str | None = None,
    last_sync_status: str | None = None,
    sync_available: bool = False,
    freshness_note: str | None = None,
) -> DoctorSnapshot:
    """Pure constructor: no repository, no I/O.

    Holdings are copied (the caller's objects are never mutated). Weights are
    always recomputed from ``market_value`` over the non-cash total; when every
    market value is 0 the given ``weight_pct`` are used as values.
    """
    copied = [AnalyzedHolding(**h.__dict__) for h in holdings]
    if copied and sum(_value_of(h) for h in copied if not is_cash_holding(h)) <= 0:
        for h in copied:
            h.market_value = max(0.0, float(h.weight_pct or 0.0))
    snapshot = DoctorSnapshot(
        portfolio_ids=sorted({int(pid) for pid in portfolio_ids}),
        holdings=copied,
        base_currency=base_currency,
        cash_value=float(cash_value or 0.0),
        price_as_of={int(k): _iso(v) if not isinstance(v, str) else v for k, v in (price_as_of or {}).items()},
        stale_asset_ids={int(a) for a in stale_asset_ids},
        missing_price_asset_ids={int(a) for a in missing_price_asset_ids},
        last_successful_price_sync=last_successful_price_sync,
        last_sync_status=last_sync_status,
        sync_available=sync_available,
        freshness_note=freshness_note,
    )
    for h in snapshot.holdings:
        h.weight_pct = snapshot.weight_of(h)
    return snapshot


def _load_scope(repo: Any, ids: list[int], user_id: str) -> tuple[str | None, float]:
    """Validate ownership of every portfolio; return (base currency, cash balance).

    Raises ValueError (not found / mixed currencies) exactly like the
    aggregate Doctor features.
    """
    engine = getattr(repo, "engine", None)
    if engine is not None and hasattr(repo, "_get_portfolio_for_user"):
        from ...repository._scope import load_scope_portfolios

        with engine.begin() as conn:
            _ids, portfolios = load_scope_portfolios(repo, conn, ids, user_id)
        return portfolios[0].base_currency, sum(float(p.cash_balance or 0.0) for p in portfolios)
    scope = repo.resolve_portfolio_scope(ids, user_id)
    return getattr(scope, "base_currency", None), 0.0


def build_snapshot(repo: Any, portfolio_ids: Iterable[int], user_id: str) -> DoctorSnapshot:
    """Snapshot of a scope (one or more portfolios) read from the repository.

    Raises ScopeError for an invalid id list and ValueError for a portfolio
    the user does not own.
    """
    ids = normalize_scope_ids(portfolio_ids)
    base_currency, cash_balance = _load_scope(repo, ids, user_id)

    if len(ids) == 1:
        positions = repo.get_positions(ids[0], user_id)
    else:
        positions = repo.get_positions_multi(ids, user_id)
    positions = [p for p in (positions or []) if float(getattr(p, "quantity", 0) or 0) > 0]

    holdings = _merge_holdings_by_asset(_holdings_from_positions(repo, positions))

    price_as_of: dict[int, str | None] = {}
    stale_ids: set[int] = set()
    missing_ids: set[int] = set()
    for p in positions:
        aid = int(p.asset_id)
        latest = _latest_price_value(p)
        iso = _iso(latest)
        previous = price_as_of.get(aid)
        # The same asset in more positions: keep the oldest timestamp.
        if aid not in price_as_of or (iso is not None and previous is not None and _to_datetime(iso) < _to_datetime(previous)):
            price_as_of[aid] = iso
        if getattr(p, "price_stale", False):
            stale_ids.add(aid)
        if latest is None or getattr(p, "price_fallback", None) == "avg_cost":
            missing_ids.add(aid)

    sync = sync_status(repo)
    stale_symbols = sorted({str(p.symbol) for p in positions if getattr(p, "price_stale", False)})
    missing_symbols = sorted({str(p.symbol) for p in positions if int(p.asset_id) in missing_ids})
    cash_positions = sum(_value_of(h) for h in holdings if is_cash_holding(h))

    return snapshot_from_holdings(
        holdings,
        portfolio_ids=ids,
        base_currency=base_currency,
        cash_value=cash_balance + cash_positions,
        price_as_of=price_as_of,
        stale_asset_ids=stale_ids,
        missing_price_asset_ids=missing_ids,
        last_successful_price_sync=sync["last_successful_price_sync"],
        last_sync_status=sync["last_sync_status"],
        sync_available=bool(sync["available"]),
        freshness_note=_note(sync, stale_symbols, missing_symbols),
    )
