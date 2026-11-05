"""Scope of a Doctor policy: the exact set of portfolios it applies to.

A policy belongs to one scope fingerprint. Single and aggregate policies are
independent (contract §3): the policy of portfolios {19, 26} is not the merge
of the policies of 19 and 26.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...schemas.doctor_policy import PolicyScope

MAX_SCOPE_PORTFOLIOS = 20


class ScopeError(ValueError):
    """Invalid list of portfolio ids (empty, too many, non-positive)."""


def normalize_scope_ids(portfolio_ids: Iterable[int]) -> list[int]:
    """Sorted, deduplicated ids. Raises ScopeError for an empty list, an id
    that is not a positive integer or more than MAX_SCOPE_PORTFOLIOS ids."""
    if portfolio_ids is None:
        raise ScopeError("Seleziona almeno un portafoglio")
    ids: set[int] = set()
    for raw in portfolio_ids:
        if isinstance(raw, bool) or not isinstance(raw, int):
            try:
                value = int(str(raw).strip())
            except (TypeError, ValueError):
                raise ScopeError(f"Identificativo di portafoglio non valido: {raw!r}") from None
        else:
            value = raw
        if value <= 0:
            raise ScopeError(f"Identificativo di portafoglio non valido: {raw!r}")
        ids.add(value)
    if not ids:
        raise ScopeError("Seleziona almeno un portafoglio")
    if len(ids) > MAX_SCOPE_PORTFOLIOS:
        raise ScopeError(f"Al massimo {MAX_SCOPE_PORTFOLIOS} portafogli per policy")
    return sorted(ids)


def scope_fingerprint(portfolio_ids: Iterable[int]) -> str:
    """``"p:" + sorted unique ids joined by commas`` (e.g. ``p:19,26``)."""
    return "p:" + ",".join(str(pid) for pid in normalize_scope_ids(portfolio_ids))


def scope_type(portfolio_ids: Iterable[int]) -> str:
    """``"single"`` for one portfolio, ``"aggregate"`` for more."""
    return "single" if len(normalize_scope_ids(portfolio_ids)) == 1 else "aggregate"


def build_scope(portfolio_ids: Iterable[int]) -> PolicyScope:
    ids = normalize_scope_ids(portfolio_ids)
    return PolicyScope(
        portfolio_ids=ids,
        scope_type="single" if len(ids) == 1 else "aggregate",
        fingerprint="p:" + ",".join(str(pid) for pid in ids),
    )
