"""Contesto memoizzato dell'Auditor (TASK-73, contratto §3.5 e §5).

Il contesto chiama i tool MCP con ``run_tool_sync`` e le stesse dipendenze del server
(``ToolDependencies``), applica ``sanitize_output`` come il server prima di rispondere al client
(senza il troncamento a 200 KB) e memoizza ogni coppia (tool, argomenti) per tutta l'esecuzione.
Le uniche letture dirette sono ``transactions`` e ``performance_audit`` (§5.4).
"""

from __future__ import annotations

import copy
import json
import logging
import threading
from collections import Counter
from datetime import UTC, date, datetime
from typing import Any, Callable, Mapping, Sequence

from app.mcp_server import tools as mcp_tools
from app.mcp_server.tools import McpToolError, ToolDependencies, sanitize_output

logger = logging.getLogger(__name__)

AGGREGATE_TOOL_OF: dict[str, str] = {
    "get_portfolio_summary": "get_aggregate_summary",
    "get_positions": "get_aggregate_positions",
    "get_performance": "get_aggregate_performance",
    "get_recent_transactions": "get_aggregate_recent_transactions",
    "get_portfolio_health": "get_aggregate_health",
    "get_monte_carlo": "get_aggregate_monte_carlo",
    "get_stress_test": "get_aggregate_stress_test",
    "get_xray_summary": "get_aggregate_xray",
}
DOCTOR_SCOPE_TOOLS: frozenset[str] = frozenset({
    "read_doctor_policy", "read_doctor_metrics", "read_doctor_violations",
    "validate_policy_draft", "build_doctor_scenario", "compare_doctor_scenarios",
})
TRANSACTIONS_TOOL = "ctx.transactions"            # nome usato nelle evidenze e nella memo
PERFORMANCE_AUDIT_TOOL = "ctx.performance_audit"

MAX_AGGREGATE_PORTFOLIOS = 20
MAX_INSTRUMENT_SYMBOL_CHARS = 64
PERFORMANCE_AUDIT_PERIOD = "1y"
PERFORMANCE_AUDIT_MAX_FLOWS = 200
_MAX_ERROR_MESSAGE_CHARS = 500
_TRANSACTION_KEYS = (
    "id", "asset_id", "symbol", "side", "trade_at", "trade_date", "quantity", "price", "fees",
    "taxes", "trade_currency",
)


class AuditToolError(RuntimeError):
    """Errore di un tool (o di una lettura diretta) durante l'audit."""

    def __init__(self, tool: str, args: Mapping[str, Any], message: str) -> None:
        super().__init__(f"{tool}: {message}")
        self.tool = tool
        self.args = args
        self.message = message

    # ``BaseException.args`` è una tupla: qui ``args`` sono gli argomenti del tool (dict).
    @property  # type: ignore[override]
    def args(self) -> dict[str, Any]:
        return self._tool_args

    @args.setter
    def args(self, value: Mapping[str, Any]) -> None:
        self._tool_args = copy.deepcopy(dict(value))


class AuditorOfflineError(RuntimeError):
    """Sollevata da OfflineFinanceClient: nessun provider esterno durante l'audit."""


class ScopeSelectionError(ValueError):
    """Selezione di portafogli non valida (id non dell'utente): errore d'uso, CLI 2."""


class OfflineFinanceClient:
    """Ogni metodo pubblico solleva AuditorOfflineError (es. get_etf_top_holdings)."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        def _offline(*_args: Any, **_kwargs: Any) -> Any:
            raise AuditorOfflineError(f"provider esterno non disponibile durante l'audit ({name})")

        _offline.__name__ = name
        return _offline

    def __repr__(self) -> str:
        return "OfflineFinanceClient()"


def build_tool_dependencies(*, offline: bool = True) -> ToolDependencies:
    """Dipendenze del server MCP: stesso repository, stesso ``PerformanceService``.

    Come ``register_mcp_routes``: nessun client justETF (l'X-Ray non scrive ``etf_enrichment``).
    Il motore usa ``DATABASE_URL`` delle impostazioni dell'app (``app.db.engine``). Con
    ``offline=True`` (sempre, per l'Auditor) il finance client non raggiunge la rete.
    """
    from app.db import engine
    from app.repository import PortfolioRepository
    from app.services.performance_service import PerformanceService

    repo = PortfolioRepository(engine)
    if offline:
        finance_client: Any = OfflineFinanceClient()
    else:  # solo per diagnosi manuali: l'Auditor non lo usa mai (§0.4)
        from app.config import get_settings
        from app.finance_client import make_finance_client

        finance_client = make_finance_client(get_settings())
    return ToolDependencies(repo=repo, performance_service=PerformanceService(repo), finance_client=finance_client)


def canonical_key(tool: str, args: Mapping[str, Any]) -> str:
    return json.dumps({"tool": tool, "args": dict(args)}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def scoped_tool_args(
    tool: str, scope: Mapping[str, Any], extra_args: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    extra = dict(extra_args or {})
    if tool.startswith("get_aggregate_"):
        raise ValueError("passare il tool del portafoglio singolo")
    kind = scope["kind"]
    if kind in ("portfolio", "instrument"):
        return tool, {"portfolio_id": scope["portfolio_id"], **extra}
    if kind == "aggregate":
        ids = list(scope["portfolio_ids"])
        if tool in DOCTOR_SCOPE_TOOLS:
            return tool, {"portfolio_id": ids[0], "portfolio_ids": ids, **extra}
        if extra or tool not in AGGREGATE_TOOL_OF:
            raise ValueError(f"{tool} non ha una variante aggregata")
        return AGGREGATE_TOOL_OF[tool], {"portfolio_ids": ids}
    raise ValueError(f"scope {kind} non ammesso per {tool}")


def scope_key(scope: Mapping[str, Any]) -> str:
    kind = scope["kind"]
    if kind == "portfolio":
        return f"portfolio:{scope['portfolio_id']}"
    if kind == "aggregate":
        return "aggregate:" + ",".join(str(i) for i in scope["portfolio_ids"])
    if kind == "instrument":
        return f"instrument:{scope['portfolio_id']}:{scope['symbol']}"
    if kind == "user":
        return "user"
    raise ValueError(f"tipo di scope sconosciuto: {kind!r}")


def _error_message(exc: BaseException) -> str:
    if isinstance(exc, McpToolError):
        message = str(getattr(exc, "message", None) or exc)
    else:
        message = f"{type(exc).__name__}: {exc}"
    return message if len(message) <= _MAX_ERROR_MESSAGE_CHARS else message[:_MAX_ERROR_MESSAGE_CHARS] + "…"


def _get(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _iso_utc(value: Any) -> tuple[str | None, str | None]:
    """(trade_at ISO 8601, trade_date YYYY-MM-DD in UTC)."""
    if isinstance(value, datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        utc = aware.astimezone(UTC)
        return utc.isoformat(), utc.date().isoformat()
    if isinstance(value, date):
        return value.isoformat(), value.isoformat()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value, value[:10]
        return _iso_utc(parsed)
    return None, None


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


def _transaction_row(item: Any) -> dict[str, Any]:
    side = _get(item, "side")
    side = getattr(side, "value", side)
    trade_at, trade_date = _iso_utc(_get(item, "trade_at"))
    asset_id = _get(item, "asset_id")
    row = {
        "id": int(_get(item, "id")),
        "asset_id": None if asset_id is None else int(asset_id),
        "symbol": _get(item, "symbol"),
        "side": None if side is None else str(side),
        "trade_at": trade_at,
        "trade_date": trade_date,
        "quantity": _float(_get(item, "quantity")),
        "price": _float(_get(item, "price")),
        "fees": _float(_get(item, "fees")) or 0.0,
        "taxes": _float(_get(item, "taxes")) or 0.0,
        "trade_currency": _get(item, "trade_currency"),
    }
    return sanitize_output({key: row[key] for key in _TRANSACTION_KEYS})


class _MemoEntry:
    __slots__ = ("done", "value", "error")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: AuditToolError | None = None


class AuditContext:
    """Contesto di un'esecuzione per un utente: memo mai condivisa fra utenti o esecuzioni."""

    user_id: str
    run_id: str
    mode: str          # "ci" | "local" | "nightly" | "agent"

    def __init__(self, deps: ToolDependencies, user_id: str, *, run_id: str, mode: str) -> None:
        self.deps = deps
        self.user_id = user_id
        self.run_id = run_id
        self.mode = mode
        self._memo: dict[str, _MemoEntry] = {}
        self._lock = threading.Lock()
        self._total = 0
        self._cache_hits = 0
        self._errors = 0
        self._by_tool: Counter[str] = Counter()

    # -- memo ---------------------------------------------------------------------------------

    def _memoized(self, tool: str, args: Mapping[str, Any], key: str, compute: Callable[[], Any]) -> Any:
        with self._lock:
            entry = self._memo.get(key)
            owner = entry is None
            if owner:
                entry = _MemoEntry()
                self._memo[key] = entry
                self._total += 1
                self._by_tool[tool] += 1
            else:
                self._cache_hits += 1
        if owner:
            try:
                entry.value = compute()
            except AuditToolError as exc:
                entry.error = exc
            except Exception as exc:  # noqa: BLE001 - ogni errore del tool diventa AuditToolError
                logger.debug("Auditor: %s ha sollevato %s", tool, type(exc).__name__)
                entry.error = AuditToolError(tool, args, _error_message(exc))
            except BaseException:
                # Interruzione (KeyboardInterrupt...): non memorizzare un esito parziale.
                with self._lock:
                    self._memo.pop(key, None)
                entry.error = AuditToolError(tool, args, "chiamata interrotta")
                entry.done.set()
                raise
            if entry.error is not None:
                with self._lock:
                    self._errors += 1
            entry.done.set()
        else:
            entry.done.wait()
        if entry.error is not None:
            error = entry.error
            raise AuditToolError(error.tool, error.args, error.message)
        return copy.deepcopy(entry.value)

    def call(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
        call_args = copy.deepcopy(dict(args))
        key = canonical_key(tool, call_args)

        def compute() -> Any:
            return sanitize_output(mcp_tools.run_tool_sync(self.deps, tool, copy.deepcopy(call_args), self.user_id))

        return self._memoized(tool, call_args, key, compute)

    def try_call(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return {"ok": True, "result": self.call(tool, args), "error": None}
        except AuditToolError as exc:
            return {"ok": False, "result": None, "error": exc.message}

    def scoped(self, tool: str, scope: Mapping[str, Any],
               extra_args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.call(*scoped_tool_args(tool, scope, extra_args))

    def portfolios(self) -> list[dict[str, Any]]:
        return self.call("list_portfolios", {})["portfolios"]

    # -- letture dirette (§5.4) ---------------------------------------------------------------

    def transactions(self, portfolio_id: int) -> list[dict[str, Any]]:
        args = {"portfolio_id": portfolio_id}

        def compute() -> list[dict[str, Any]]:
            items = self.deps.repo.list_transactions(portfolio_id, self.user_id)
            rows = [_transaction_row(item) for item in items]
            rows.sort(key=lambda r: r["id"], reverse=True)
            rows.sort(key=lambda r: _sort_instant(r["trade_at"]), reverse=True)
            return rows

        return self._memoized(TRANSACTIONS_TOOL, args, canonical_key(TRANSACTIONS_TOOL, args), compute)

    def performance_audit(self, portfolio_ids: Sequence[int]) -> dict[str, Any]:
        ids = sorted({int(i) for i in portfolio_ids})
        if not ids:
            raise ValueError("performance_audit richiede almeno un portafoglio")
        args = {"portfolio_ids": ids}
        if len(ids) >= 2:
            try:
                return self.call("get_aggregate_performance_audit", args)
            except AuditToolError as exc:
                raise AuditToolError(PERFORMANCE_AUDIT_TOOL, args, exc.message) from exc
        pid = ids[0]

        def compute() -> dict[str, Any]:
            from app.services.performance_audit import build_performance_audit_export

            export = build_performance_audit_export(
                self.deps.performance_service, pid, self.user_id,
                period=PERFORMANCE_AUDIT_PERIOD, max_flows=PERFORMANCE_AUDIT_MAX_FLOWS, offset=0,
            )
            return sanitize_output(export)

        return self._memoized(PERFORMANCE_AUDIT_TOOL, args, canonical_key(PERFORMANCE_AUDIT_TOOL, args), compute)

    def call_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total": self._total,
                "cache_hits": self._cache_hits,
                "errors": self._errors,
                "by_tool": dict(sorted(self._by_tool.items())),
            }


def _sort_instant(value: str | None) -> float:
    if not value:
        return float("-inf")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return float("-inf")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def discover_scopes(
    ctx: AuditContext, *, portfolio_ids: Sequence[int] | None = None,
    include_aggregate: bool = True, include_instruments: bool = True,
) -> list[dict[str, Any]]:
    """Scope dell'esecuzione (§5.3), in ordine di ``scope_key``.

    Un id in ``portfolio_ids`` che non è dell'utente solleva ``ScopeSelectionError``.
    """
    portfolios = ctx.portfolios()
    by_id = {int(p["id"]): p for p in portfolios}
    if portfolio_ids is None:
        selected_ids = sorted(by_id)
    else:
        wanted = sorted({int(i) for i in portfolio_ids})
        foreign = [i for i in wanted if i not in by_id]
        if foreign:
            raise ScopeSelectionError(
                "portafogli non trovati per l'utente: " + ", ".join(str(i) for i in foreign)
            )
        selected_ids = wanted

    scopes: list[dict[str, Any]] = [{"kind": "portfolio", "portfolio_id": pid} for pid in selected_ids]

    if include_aggregate:
        by_currency: dict[str, list[int]] = {}
        for pid in selected_ids:
            currency = str(by_id[pid].get("base_currency") or "")
            by_currency.setdefault(currency, []).append(pid)
        for ids in by_currency.values():
            if len(ids) >= 2:
                scopes.append({"kind": "aggregate", "portfolio_ids": sorted(ids)[:MAX_AGGREGATE_PORTFOLIOS]})

    if include_instruments:
        for pid in selected_ids:
            try:
                positions = ctx.scoped("get_positions", {"kind": "portfolio", "portfolio_id": pid}).get("positions") or []
            except AuditToolError as exc:
                # Le regole sul portafoglio riceveranno lo stesso errore (memo): qui niente scope.
                logger.warning("Auditor: get_positions non disponibile per uno scope: %s", type(exc).__name__)
                continue
            seen: set[str] = set()
            for row in positions[:30]:
                symbol = row.get("symbol") if isinstance(row, Mapping) else None
                if not isinstance(symbol, str) or not symbol or len(symbol) > MAX_INSTRUMENT_SYMBOL_CHARS:
                    continue
                if symbol in seen:
                    continue
                seen.add(symbol)
                scopes.append({"kind": "instrument", "portfolio_id": pid, "symbol": symbol})

    if selected_ids:
        scopes.append({"kind": "user", "portfolio_ids": list(selected_ids)})

    return sorted(scopes, key=scope_key)
