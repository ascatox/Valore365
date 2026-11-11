"""TASK-76 — regole del gruppo C (costi, reddito, dividendi, Monte Carlo, variazioni giornaliere).

Per ogni regola: pass su dati corretti, fail quando si reintroduce il difetto del finding, skip con il
codice giusto quando i dati mancano. Gli output dei tool sono prodotti dai **veri handler** di
``app/copilot_tools.py`` su un repository finto (portafogli di prova di ``docs/auditor/rules.md`` §1),
passati da ``sanitize_output`` come fa il server MCP; i difetti si reintroducono con un monkeypatch del
codice corretto o riproducendo l'output sbagliato del finding.
"""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import pytest

from app import copilot_tools as ct
from app.mcp_server.tools import sanitize_output
from app.services.asset_classification import classify_asset
from app.services.auditor.rules import costs_income as rules
from app.services.portfolio_doctor import _health
from app.services.portfolio_doctor._monte_carlo import _simulate_paths

# ---------------------------------------------------------------------------
# Contesto finto di riferimento (docs/auditor/architecture.md §10, copiato)
# ---------------------------------------------------------------------------

AGGREGATE_TOOL_OF = {
    "get_portfolio_summary": "get_aggregate_summary", "get_positions": "get_aggregate_positions",
    "get_performance": "get_aggregate_performance", "get_recent_transactions": "get_aggregate_recent_transactions",
    "get_portfolio_health": "get_aggregate_health", "get_monte_carlo": "get_aggregate_monte_carlo",
    "get_stress_test": "get_aggregate_stress_test", "get_xray_summary": "get_aggregate_xray",
}
DOCTOR_SCOPE_TOOLS = frozenset({
    "read_doctor_policy", "read_doctor_metrics", "read_doctor_violations",
    "validate_policy_draft", "build_doctor_scenario", "compare_doctor_scenarios",
})


def canonical_key(tool: str, args: Mapping[str, Any]) -> str:
    return json.dumps({"tool": tool, "args": dict(args)}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def scoped_tool_args(tool: str, scope: Mapping[str, Any], extra_args: Mapping[str, Any] | None = None):
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


class FakeToolError(RuntimeError):
    def __init__(self, tool: str, args: Mapping[str, Any], message: str) -> None:
        super().__init__(f"{tool}: {message}")
        self.tool, self.args, self.message = tool, dict(args), message


class FakeAuditContext:
    """responses: [(tool, args, result_dict | Exception)]; transactions: {pid: [tx]};
    performance_audit: {tuple(sorted(ids)): export}; portfolios: [{"id", "name", "base_currency"}]."""

    def __init__(self, responses=(), *, transactions=None, performance_audit=None, portfolios=None,
                 user_id: str = "test-user") -> None:
        self.user_id, self.run_id, self.mode = user_id, "0" * 32, "local"
        self._responses = {canonical_key(t, a): r for t, a, r in responses}
        self._transactions = dict(transactions or {})
        self._performance_audit = dict(performance_audit or {})
        if portfolios is not None:
            self._responses[canonical_key("list_portfolios", {})] = {"portfolios": list(portfolios)}
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append((tool, dict(args)))
        key = canonical_key(tool, args)
        if key not in self._responses:
            raise KeyError(f"risposta finta mancante: {key}")
        value = self._responses[key]
        if isinstance(value, Exception):
            raise FakeToolError(tool, args, str(value))
        return copy.deepcopy(value)

    def try_call(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return {"ok": True, "result": self.call(tool, args), "error": None}
        except FakeToolError as exc:
            return {"ok": False, "result": None, "error": exc.message}

    def scoped(self, tool: str, scope: Mapping[str, Any], extra_args: Mapping[str, Any] | None = None):
        return self.call(*scoped_tool_args(tool, scope, extra_args))

    def portfolios(self) -> list[dict[str, Any]]:
        return self.call("list_portfolios", {})["portfolios"]

    def transactions(self, portfolio_id: int) -> list[dict[str, Any]]:
        return copy.deepcopy(self._transactions[portfolio_id])

    def performance_audit(self, portfolio_ids: Sequence[int]) -> dict[str, Any]:
        return copy.deepcopy(self._performance_audit[tuple(sorted(portfolio_ids))])

    def call_stats(self) -> dict[str, Any]:
        return {"total": len(self.calls), "cache_hits": 0, "errors": 0, "by_tool": {}}


# ---------------------------------------------------------------------------
# Validazione degli esiti contro $defs/Outcome dello schema
# ---------------------------------------------------------------------------

_SCHEMA_PATH = Path(__file__).resolve().parents[4] / "docs" / "auditor" / "schemas" / "report.schema.json"


@lru_cache(maxsize=1)
def _outcome_validator():
    try:
        import jsonschema
    except ImportError:  # pragma: no cover
        return None
    if not _SCHEMA_PATH.exists():  # pragma: no cover
        return None
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator({"$ref": "#/$defs/Outcome", "$defs": schema["$defs"]})


def run_rule(rule_id: str, ctx: FakeAuditContext, scope: dict) -> dict:
    decl = next(r for r in rules.RULES if r["id"] == rule_id)
    assert scope["kind"] in decl["scopes"]
    outcome = decl["check"](ctx, copy.deepcopy(scope))
    json.dumps(outcome)  # serializzabile
    validator = _outcome_validator()
    if validator is not None:
        validator.validate(outcome)
    return outcome


def assert_status(outcome: dict, status: str, code: str | None = None) -> None:
    assert outcome["status"] == status, outcome
    if code is not None:
        assert outcome["reason_code"] == code, outcome


# ---------------------------------------------------------------------------
# Portafogli di prova (rules.md §1) e repository finto
# ---------------------------------------------------------------------------

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
USER = "test-user"

# asset_id: symbol, name, asset_type, justETF (focus, TER), yFinance (expense_ratio, category, dividend_yield)
ASSETS: dict[int, dict[str, Any]] = {
    9201: {"symbol": "AUDEQ.MI", "name": "AUD Global Equity UCITS ETF (Acc)", "asset_type": "etf",
           "focus": "Equity, World", "ter": 0.22},
    9202: {"symbol": "AUDBD.MI", "name": "AUD Global Aggregate Bond UCITS ETF EUR Hedged (Acc)", "asset_type": "etf",
           "focus": "Bonds, World, Aggregate", "ter": 0.10},
    9203: {"symbol": "AUDTECH.DE", "name": "AUD Nasdaq-100 Technology UCITS ETF (Dist)", "asset_type": "etf",
           "focus": "Equity, United States, Technology", "ter": 0.30, "dividend_yield": 0.6},
    9204: {"symbol": "AUDGOV.MI", "name": "AUD Euro Government Bond UCITS ETF (Dist)", "asset_type": "etf",
           "focus": "Bonds, Euro, Government", "ter": 0.15, "dividend_yield": 2.5},
    9205: {"symbol": "AUDHY.DE", "name": "AUD Euro High Yield Corporate Bond UCITS ETF (Dist)", "asset_type": "stock",
           "expense_ratio": 0.005, "category": "High Yield Bond", "dividend_yield": 5.0},
    9206: {"symbol": "AUDBTP", "name": "BTP Italia 2030 1,6%", "asset_type": "bond", "dividend_yield": 1.6},
    9207: {"symbol": "AUDGLD.DE", "name": "AUD Physical Gold ETC", "asset_type": "stock",
           "focus": "Precious Metals, Gold", "ter": 0.25},
    9208: {"symbol": "AUDCMD.MI", "name": "AUD Broad Commodity Swap UCITS ETF", "asset_type": "etf",
           "focus": "Commodities, Broad market", "ter": 0.19},
    9209: {"symbol": "AUDTHM.DE", "name": "AUD Thematic Frontier Opportunities UCITS ETF", "asset_type": "etf"},
    9210: {"symbol": "AUDUS.L", "name": "AUD World Equity UCITS ETF USD (Acc)", "asset_type": "etf",
           "focus": "Equity, World", "ter": 0.20, "quote_currency": "USD"},
    9211: {"symbol": "AUDUK.L", "name": "AUD UK Gilts UCITS ETF GBP (Dist)", "asset_type": "etf",
           "focus": "Bonds, United Kingdom, Government", "ter": 0.07, "dividend_yield": 3.0, "quote_currency": "GBP"},
    9212: {"symbol": "AUDSTL.MI", "name": "AUD Europe Equity UCITS ETF (Acc)", "asset_type": "etf",
           "focus": "Equity, Europe", "ter": 0.12},
    9213: {"symbol": "AUDNPC.MI", "name": "AUD Emerging Markets Equity UCITS ETF (Acc)", "asset_type": "etf",
           "focus": "Equity, Emerging Markets", "ter": 0.18},
}
SYMBOL_ID = {a["symbol"]: aid for aid, a in ASSETS.items()}


def holding(symbol: str, market_value: float, *, day_change_pct: float = 0.0, previous_close: bool = True,
            stale: bool = False, price_date: date | None = TODAY) -> dict[str, Any]:
    return {"symbol": symbol, "market_value": market_value, "day_change_pct": day_change_pct,
            "previous_close": previous_close, "stale": stale, "price_date": price_date}


# Composizioni: valori in EUR, variazioni giornaliere del giorno.
PORTFOLIOS: dict[int, list[dict[str, Any]]] = {
    9101: [holding("AUDEQ.MI", 7000.0, day_change_pct=0.8512), holding("AUDBD.MI", 2000.0, day_change_pct=-0.1234),
           holding("AUDTECH.DE", 1000.0, day_change_pct=1.4021)],
    9102: [holding("AUDGOV.MI", 4000.0, day_change_pct=0.05), holding("AUDHY.DE", 3500.0, day_change_pct=-0.21),
           holding("AUDBTP", 2500.0, day_change_pct=0.02)],
    9103: [holding("AUDGLD.DE", 4000.0, day_change_pct=0.6), holding("AUDEQ.MI", 2500.0, day_change_pct=0.8512),
           holding("AUDCMD.MI", 2000.0, day_change_pct=-0.4), holding("AUDTHM.DE", 1500.0, day_change_pct=0.3)],
    9104: [holding("AUDUS.L", 5000.0, day_change_pct=0.4), holding("AUDUK.L", 3000.0, day_change_pct=-0.1),
           holding("AUDEQ.MI", 2000.0, day_change_pct=0.8512)],
    9105: [holding("AUDEQ.MI", 6000.0, day_change_pct=0.8512), holding("AUDBD.MI", 4000.0, day_change_pct=-0.1234)],
    9106: [],
    9107: [holding("AUDEQ.MI", 3000.0, day_change_pct=0.8512),
           holding("AUDSTL.MI", 2000.0, stale=True, price_date=TODAY - timedelta(days=30)),
           holding("AUDNPC.MI", 1000.0, previous_close=False)],
}


def _dividend(asset: str, days_ago: int, amount: float, currency: str, tx_id: int) -> dict[str, Any]:
    trade_at = datetime.combine(TODAY - timedelta(days=days_ago), datetime.min.time(), tzinfo=timezone.utc)
    return {"id": tx_id, "asset_id": SYMBOL_ID[asset], "symbol": asset, "side": "dividend",
            "trade_at": trade_at, "quantity": 1.0, "price": amount, "fees": 0.0, "taxes": 0.0,
            "trade_currency": currency}


TRANSACTIONS: dict[int, list[dict[str, Any]]] = {
    9101: [_dividend("AUDTECH.DE", 40, 3.15, "EUR", 1), _dividend("AUDTECH.DE", 220, 2.85, "EUR", 2)],
    9102: [],
    9103: [],
    9104: [_dividend("AUDUK.L", 30, 22.5, "GBP", 3), _dividend("AUDUK.L", 210, 21.75, "GBP", 4),
           _dividend("AUDEQ.MI", 100, 12.4, "EUR", 5)],
    9105: [_dividend("AUDEQ.MI", 30 * m + 5, 10.0 + m * 0.1, "EUR", 10 + m) for m in range(6)],
    9106: [],
    9107: [],
}


class StubRepo:
    """Le letture di PortfolioRepository usate dai tool del gruppo C, sui portafogli di prova."""

    def __init__(self, portfolios: Mapping[int, list[dict]] = PORTFOLIOS,
                 transactions: Mapping[int, list[dict]] = TRANSACTIONS) -> None:
        self._portfolios = portfolios
        self._transactions = transactions

    def _position(self, h: dict, total: float) -> SimpleNamespace:
        aid = SYMBOL_ID[h["symbol"]]
        a = ASSETS[aid]
        mv = h["market_value"]
        price = 100.0
        return SimpleNamespace(
            asset_id=aid, symbol=a["symbol"], name=a["name"], asset_type=a["asset_type"],
            investment_focus=a.get("focus"), quantity=mv / price, avg_cost=price * 0.95, market_price=price,
            market_value=mv, weight=mv / total * 100.0 if total else 0.0, unrealized_pl_pct=5.26,
            day_change_pct=h["day_change_pct"] if h["previous_close"] and not h["stale"] else 0.0,
            price_date=h["price_date"], price_stale=h["stale"],
            stale_reason="quotazione ferma da 30 giorni" if h["stale"] else None,
            last_price_at=None, price_fallback=None, fx_missing=False,
            previous_close_available=h["previous_close"],
        )

    def get_positions(self, portfolio_id: int, _user_id: str) -> list[SimpleNamespace]:
        rows = self._portfolios[portfolio_id]
        total = sum(h["market_value"] for h in rows)
        return [self._position(h, total) for h in rows]

    def get_summary(self, portfolio_id: int, _user_id: str) -> SimpleNamespace:
        total = sum(h["market_value"] for h in self._portfolios[portfolio_id])
        return SimpleNamespace(market_value=total, cost_basis=total * 0.95)

    def get_user_settings(self, _user_id: str):
        raise LookupError("nessuna impostazione")

    def list_transactions(self, portfolio_id: int, _user_id: str) -> list[SimpleNamespace]:
        return [SimpleNamespace(**t) for t in self._transactions[portfolio_id]]

    def get_asset(self, asset_id: int) -> SimpleNamespace:
        a = ASSETS[asset_id]
        return SimpleNamespace(symbol=a["symbol"], name=a["name"], asset_type=a["asset_type"],
                               quote_currency=a.get("quote_currency", "EUR"), isin=None)

    def _meta(self, asset_id: int) -> SimpleNamespace | None:
        a = ASSETS[asset_id]
        if not any(k in a for k in ("expense_ratio", "category", "dividend_yield")):
            return None
        return SimpleNamespace(expense_ratio=a.get("expense_ratio"), raw_info=None, category=a.get("category"),
                               dividend_yield=a.get("dividend_yield"), description=None)

    def get_asset_metadata(self, asset_id: int):
        return self._meta(asset_id)

    def get_asset_metadata_bulk(self, asset_ids):
        return {aid: m for aid in asset_ids if (m := self._meta(aid)) is not None}

    def get_etf_enrichment(self, asset_id: int):
        a = ASSETS[asset_id]
        return {"investment_focus": a["focus"], "ter": a.get("ter")} if "focus" in a else None

    def get_etf_enrichment_bulk(self, asset_ids):
        return {aid: {"ter": ASSETS[aid]["ter"]} for aid in asset_ids if ASSETS[aid].get("ter") is not None}


@pytest.fixture
def repo(monkeypatch) -> StubRepo:
    stub = StubRepo()

    def load_holdings(_repo, portfolio_id, _user_id):
        return [SimpleNamespace(asset_id=p.asset_id, asset_type=p.asset_type, symbol=p.symbol, name=p.name)
                for p in stub.get_positions(portfolio_id, USER)]

    def classification_inputs(_repo, asset_ids):
        return {aid: {"isin": None, "investment_focus": ASSETS[aid].get("focus"), "index_tracked": None,
                      "category": ASSETS[aid].get("category"), "enrichment_name": None} for aid in asset_ids}

    monkeypatch.setattr(ct, "_load_holdings", load_holdings)
    monkeypatch.setattr(ct, "load_classification_inputs", classification_inputs)
    monkeypatch.setattr(ct, "run_monte_carlo_projection", _fake_monte_carlo)
    return stub


@lru_cache(maxsize=None)
def _paths(mu: float, sigma: float, df: float):
    return tuple(_simulate_paths(mu, sigma, df))


MC_PARAMS = {9101: (0.056, 0.115, 8.0), 9103: (0.044, 0.14, 6.0), 9102: (0.03, 0.05, 12.0)}


def _fake_monte_carlo(_repo, portfolio_id, _user_id):
    """run_monte_carlo_projection con la vera simulazione (_simulate_paths, seed 42)."""
    key = tuple(portfolio_id) if isinstance(portfolio_id, list) else portfolio_id
    if key == 9106 or key == 9107:  # 9106 vuoto, 9107 senza storico
        return SimpleNamespace(projections=[], annualized_mean_return_pct=0.0, annualized_volatility_pct=0.0)
    mu, sigma, df = MC_PARAMS.get(key, (0.05, 0.10, 10.0))
    return SimpleNamespace(projections=list(_paths(mu, sigma, df)), annualized_mean_return_pct=round(mu * 100, 2),
                           annualized_volatility_pct=round(sigma * 100, 2))


def tool(name: str, repo: StubRepo, pid: Any, args: Mapping[str, Any] | None = None) -> dict:
    """Output di un vero handler, come lo vede il client MCP."""
    handler = ct._TOOL_HANDLERS[name]
    return sanitize_output(handler(dict(args or {}), repo, None, pid, USER))


def tx_dicts(pid: int) -> list[dict]:
    """ctx.transactions: chiavi e ordinamento di architecture.md §5.4."""
    rows = []
    for t in sorted(TRANSACTIONS[pid], key=lambda t: (t["trade_at"], t["id"]), reverse=True):
        rows.append({**t, "trade_at": t["trade_at"].isoformat(), "trade_date": t["trade_at"].date().isoformat()})
    return rows


C_TOOLS = ("get_positions", "get_cost_breakdown", "get_income_projection", "get_dividend_summary",
           "get_monte_carlo", "get_day_movers")


def portfolio_ctx(repo: StubRepo, pid: int, overrides: Mapping[str, Any] | None = None) -> FakeAuditContext:
    """Contesto finto con gli output reali dei tool per il portafoglio ``pid``; ``overrides`` sostituisce
    l'output di un tool (difetto riprodotto)."""
    overrides = dict(overrides or {})
    args = {"portfolio_id": pid}
    responses = [(name, args, overrides.get(name) or tool(name, repo, pid)) for name in C_TOOLS]
    for p in repo.get_positions(pid, USER):
        info_args = {"portfolio_id": pid, "symbol": p.symbol}
        responses.append(("search_asset_info", info_args, tool("search_asset_info", repo, pid, {"symbol": p.symbol})))
    return FakeAuditContext(responses, transactions={pid: tx_dicts(pid)})


def scope_of(pid: int) -> dict:
    return {"kind": "portfolio", "portfolio_id": pid}


AGG_IDS = [9101, 9103]
AGG_SCOPE = {"kind": "aggregate", "portfolio_ids": AGG_IDS}


def aggregate_ctx(repo: StubRepo, mc_override: dict | None = None) -> FakeAuditContext:
    rows = [ct.position_row(p) for pid in AGG_IDS for p in repo.get_positions(pid, USER)]
    positions = sanitize_output({"positions_count": len(rows), "positions": rows})
    mc = mc_override or tool("get_monte_carlo", repo, list(AGG_IDS))
    args = {"portfolio_ids": AGG_IDS}
    return FakeAuditContext([("get_aggregate_positions", args, positions), ("get_aggregate_monte_carlo", args, mc)])


# ---------------------------------------------------------------------------
# Dichiarazioni
# ---------------------------------------------------------------------------

CATALOG = {
    "C-TER-RANGE": ("P1", "costs", ["V-TER-UNIT", "V365-007"], ["portfolio"]),
    "C-COST-COHERENCE": ("P1", "costs", ["V365-007"], ["portfolio"]),
    "C-COST-COVERAGE-DECLARED": ("P1", "costs", ["V365-007"], ["portfolio"]),
    "C-INCOME-BUCKETS-SUM": ("P1", "income", ["V365-004"], ["portfolio"]),
    "C-INCOME-CLASS-RECOMPUTE": ("P1", "income", ["V365-004", "V-INCOME-TYPE"], ["portfolio"]),
    "C-MC-YEARS": ("P1", "montecarlo", ["V365-006"], ["portfolio", "aggregate"]),
    "C-MC-PERCENTILES": ("P1", "montecarlo", ["V365-006"], ["portfolio", "aggregate"]),
    "C-MC-MEDIAN-DRIFT": ("P2", "montecarlo", ["V365-006"], ["portfolio", "aggregate"]),
    "C-DIV-CURRENCY": ("P2", "income", ["V-DIV-MIXED-CCY", "V365-009"], ["portfolio"]),
    "C-DAYMOVERS-NONZERO-INCLUDED": ("P1", "daily", ["V365-005", "V-DAYMOVERS-ROOT"], ["portfolio"]),
    "C-DAYMOVERS-CONSISTENCY": ("P1", "daily", ["V-DAYMOVERS-ROOT", "V365-005"], ["portfolio"]),
    "C-DAYCHANGE-DENOMINATOR": ("P2", "daily", ["S-2026-11-11-03"], ["portfolio"]),
}


def test_declarations_match_catalog():
    import re

    assert [r["id"] for r in rules.RULES] == list(CATALOG)
    for decl in rules.RULES:
        severity, area, findings, scopes = CATALOG[decl["id"]]
        assert re.match(r"^[ABCD]-[A-Z0-9]+(?:-[A-Z0-9]+)*$", decl["id"])
        assert decl["group"] == "C"
        assert (decl["severity"], decl["area"], decl["findings"], decl["scopes"]) == (severity, area, findings, scopes)
        assert decl["title"] and callable(decl["check"]) and decl["tools"]
        assert set(decl) <= {"id", "group", "title", "area", "severity", "findings", "scopes", "tools", "check",
                             "timeout_s", "known_defect"}


def test_module_imports_only_stdlib():
    source = Path(rules.__file__).read_text(encoding="utf-8")
    imports = [line.split()[1] for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert set(imports) <= {"__future__", "math", "typing"}


# ---------------------------------------------------------------------------
# C-TER-RANGE (V-TER-UNIT)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9102, 9103])
def test_ter_range_passes(repo, pid):
    assert_status(run_rule("C-TER-RANGE", portfolio_ctx(repo, pid), scope_of(pid)), "pass")


def test_ter_range_fails_without_expense_ratio_normalization(repo, monkeypatch):
    # V-TER-UNIT: expense_ratio yFinance (frazione 0,005) letto senza normalize_expense_ratio_pct.
    monkeypatch.setattr(_health, "normalize_expense_ratio_pct", lambda value: value)
    outcome = run_rule("C-TER-RANGE", portfolio_ctx(repo, 9102), scope_of(9102))
    assert_status(outcome, "fail", "invariant_violated")
    assert any(e["path"] == "position_costs[symbol=AUDHY.DE].ter_pct" and e["observed"] == 0.005
               for e in outcome["evidence"])


def test_ter_range_fails_on_hundredfold_ter(repo):
    cb = tool("get_cost_breakdown", repo, 9101)
    for row in cb["position_costs"]:
        row["ter_pct"] = round(row["ter_pct"] * 100, 3)  # 0,22 → 22
    outcome = run_rule("C-TER-RANGE", portfolio_ctx(repo, 9101, {"get_cost_breakdown": cb}), scope_of(9101))
    assert_status(outcome, "fail")


def test_ter_range_skips(repo):
    assert_status(run_rule("C-TER-RANGE", portfolio_ctx(repo, 9106), scope_of(9106)), "skip", "empty_portfolio")
    only_missing = StubRepo({9301: [holding("AUDTHM.DE", 1000.0)]}, {9301: []})
    ctx = FakeAuditContext([("get_cost_breakdown", {"portfolio_id": 9301},
                             _cost_with(only_missing, 9301))])
    assert_status(run_rule("C-TER-RANGE", ctx, scope_of(9301)), "skip", "no_reference_data")


def _cost_with(stub: StubRepo, pid: int) -> dict:
    holdings = [SimpleNamespace(asset_id=p.asset_id, asset_type=p.asset_type, symbol=p.symbol, name=p.name)
                for p in stub.get_positions(pid, USER)]
    original = ct._load_holdings
    ct._load_holdings = lambda *_a: holdings
    try:
        return tool("get_cost_breakdown", stub, pid)
    finally:
        ct._load_holdings = original


# ---------------------------------------------------------------------------
# C-COST-COHERENCE (V365-007)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9102, 9103])
def test_cost_coherence_passes(repo, pid):
    assert_status(run_rule("C-COST-COHERENCE", portfolio_ctx(repo, pid), scope_of(pid)), "pass")


def test_cost_coherence_passes_without_coverage(repo):
    stub = StubRepo({9301: [holding("AUDTHM.DE", 1000.0)]}, {9301: []})
    cb = _cost_with(stub, 9301)
    assert cb["weighted_ter_pct"] is None
    ctx = FakeAuditContext([("get_cost_breakdown", {"portfolio_id": 9301}, cb)])
    assert_status(run_rule("C-COST-COHERENCE", ctx, scope_of(9301)), "pass")


def test_cost_coherence_fails_on_cost_over_total_value(repo):
    # V365-007: costo annuo sul valore totale con il TER medio del solo perimetro coperto (9103: AUDTHM.DE senza TER).
    cb = tool("get_cost_breakdown", repo, 9103)
    assert cb["ter_coverage_pct"] < 100
    total, w = cb["portfolio_market_value"], cb["weighted_ter_pct"]
    cb["estimated_annual_cost_known_eur"] = cb["total_annual_cost_eur"] = round(total * w / 100, 2)
    cb["fee_drag_10y_eur"] = round(total * (1 - (1 - w / 100) ** 10), 2)
    outcome = run_rule("C-COST-COHERENCE", portfolio_ctx(repo, 9103, {"get_cost_breakdown": cb}), scope_of(9103))
    assert_status(outcome, "fail", "invariant_violated")
    paths = {e["path"] for e in outcome["evidence"]}
    assert {"estimated_annual_cost_known_eur", "fee_drag_10y_eur"} <= paths


def test_cost_coherence_fails_on_legacy_key_and_null_ter(repo):
    cb = tool("get_cost_breakdown", repo, 9101)
    cb["total_annual_cost_eur"] = None
    assert_status(run_rule("C-COST-COHERENCE", portfolio_ctx(repo, 9101, {"get_cost_breakdown": cb}), scope_of(9101)),
                  "fail")
    stub = StubRepo({9301: [holding("AUDTHM.DE", 1000.0)]}, {9301: []})
    cb = _cost_with(stub, 9301)
    cb["estimated_annual_cost_known_eur"] = 2.2
    ctx = FakeAuditContext([("get_cost_breakdown", {"portfolio_id": 9301}, cb)])
    assert_status(run_rule("C-COST-COHERENCE", ctx, scope_of(9301)), "fail")


def test_cost_coherence_skips_empty(repo):
    assert_status(run_rule("C-COST-COHERENCE", portfolio_ctx(repo, 9106), scope_of(9106)), "skip", "empty_portfolio")


# ---------------------------------------------------------------------------
# C-COST-COVERAGE-DECLARED (V365-007)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9102, 9103])
def test_coverage_declared_passes(repo, pid):
    outcome = run_rule("C-COST-COVERAGE-DECLARED", portfolio_ctx(repo, pid), scope_of(pid))
    assert_status(outcome, "pass")


def test_coverage_declared_fails_on_silent_missing_ter(repo):
    # V365-007: TER mancante escluso in silenzio (missing_ter_symbols vuoto con copertura < 100).
    cb = tool("get_cost_breakdown", repo, 9103)
    assert cb["missing_ter_symbols"] == ["AUDTHM.DE"]
    cb["missing_ter_symbols"] = []
    cb["coverage_note"] = None
    outcome = run_rule("C-COST-COVERAGE-DECLARED", portfolio_ctx(repo, 9103, {"get_cost_breakdown": cb}),
                       scope_of(9103))
    assert_status(outcome, "fail", "invariant_violated")


def test_coverage_declared_fails_on_undeclared_inferred(repo):
    cb = tool("get_cost_breakdown", repo, 9102)
    assert cb["inferred_ter_symbols"] == ["AUDBTP"]
    cb["inferred_ter_symbols"] = []
    assert_status(run_rule("C-COST-COVERAGE-DECLARED", portfolio_ctx(repo, 9102, {"get_cost_breakdown": cb}),
                           scope_of(9102)), "fail")


def test_coverage_declared_skips_empty(repo):
    assert_status(run_rule("C-COST-COVERAGE-DECLARED", portfolio_ctx(repo, 9106), scope_of(9106)),
                  "skip", "empty_portfolio")


# ---------------------------------------------------------------------------
# C-INCOME-BUCKETS-SUM (V365-004)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9102, 9104])
def test_income_buckets_sum_passes(repo, pid):
    assert_status(run_rule("C-INCOME-BUCKETS-SUM", portfolio_ctx(repo, pid), scope_of(pid)), "pass")


def test_income_buckets_sum_fails_when_fixed_income_left_out(repo):
    # V365-004: reddito obbligazionario escluso dai bucket (somma dei bucket < lordo).
    inc = tool("get_income_projection", repo, 9102)
    assert inc["fixed_income_annual_dividends_eur"] > 0
    inc["fixed_income_annual_dividends_eur"] = 0.0
    outcome = run_rule("C-INCOME-BUCKETS-SUM", portfolio_ctx(repo, 9102, {"get_income_projection": inc}),
                       scope_of(9102))
    assert_status(outcome, "fail", "invariant_violated")


def test_income_buckets_sum_fails_on_projection_years_and_net(repo):
    inc = tool("get_income_projection", repo, 9101)
    inc["projections"] = inc["projections"][:2]
    inc["current_annual_dividends_net_eur"] = inc["current_annual_dividends_gross_eur"]
    outcome = run_rule("C-INCOME-BUCKETS-SUM", portfolio_ctx(repo, 9101, {"get_income_projection": inc}),
                       scope_of(9101))
    assert_status(outcome, "fail")
    assert {"projections[*].years", "current_annual_dividends_net_eur"} <= {e["path"] for e in outcome["evidence"]}


def test_income_buckets_sum_skips_empty(repo):
    assert_status(run_rule("C-INCOME-BUCKETS-SUM", portfolio_ctx(repo, 9106), scope_of(9106)),
                  "skip", "empty_portfolio")


# ---------------------------------------------------------------------------
# C-INCOME-CLASS-RECOMPUTE (V365-004, V-INCOME-TYPE)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9102, 9104])
def test_income_class_recompute_passes(repo, pid):
    assert_status(run_rule("C-INCOME-CLASS-RECOMPUTE", portfolio_ctx(repo, pid), scope_of(pid)), "pass")


def test_income_class_bond_etf_typed_stock_is_fixed_income(repo):
    inc = tool("get_income_projection", repo, 9102)
    # AUDHY.DE (tipizzato stock) 3500 × 5% + AUDGOV.MI 4000 × 2,5% + AUDBTP 2500 × 1,6% tutto a reddito fisso.
    assert inc["fixed_income_annual_dividends_eur"] == pytest.approx(175.0 + 100.0 + 40.0)
    assert inc["equity_annual_dividends_eur"] == 0.0


def test_income_class_recompute_fails_when_everything_is_equity(repo, monkeypatch):
    # V-INCOME-TYPE: asset_type letto da get_asset_by_symbol (assente) → tutto il reddito in equity.
    monkeypatch.setattr(ct, "classify_asset_class", lambda **_kw: "equity")
    ctx = portfolio_ctx(repo, 9102)
    outcome = run_rule("C-INCOME-CLASS-RECOMPUTE", ctx, scope_of(9102))
    assert_status(outcome, "fail", "invariant_violated")
    by_path = {e["path"]: e for e in outcome["evidence"]}
    assert by_path["fixed_income_annual_dividends_eur"]["observed"] == 0.0
    assert by_path["equity_annual_dividends_eur"]["expected"] == 0.0
    # La somma dei bucket resta uguale al lordo: solo il ricalcolo per classe intercetta il difetto.
    assert_status(run_rule("C-INCOME-BUCKETS-SUM", ctx, scope_of(9102)), "pass")


def test_income_class_recompute_skips(repo):
    assert_status(run_rule("C-INCOME-CLASS-RECOMPUTE", portfolio_ctx(repo, 9106), scope_of(9106)),
                  "skip", "empty_portfolio")
    # 9103: nessuna posizione con dividend_yield.
    assert_status(run_rule("C-INCOME-CLASS-RECOMPUTE", portfolio_ctx(repo, 9103), scope_of(9103)),
                  "skip", "no_reference_data")
    rows = [{"symbol": f"S{i}", "market_value": 10.0} for i in range(30)]
    ctx = FakeAuditContext([("get_positions", {"portfolio_id": 9301}, {"positions": rows})])
    assert_status(run_rule("C-INCOME-CLASS-RECOMPUTE", ctx, scope_of(9301)), "skip", "truncated_output")


def test_income_class_uses_search_asset_info_class(repo):
    info = tool("search_asset_info", repo, 9102, {"symbol": "AUDHY.DE"})
    assert info["type"] == "stock" and info["asset_class"] == "bond" and info["dividend_yield"] == 5.0
    expected = classify_asset(asset_type="stock", name=ASSETS[9205]["name"], symbol="AUDHY.DE", isin=None,
                              investment_focus=None, index_tracked=None, category="High Yield Bond",
                              enrichment_name=None)
    assert expected.asset_class == "bond"


# ---------------------------------------------------------------------------
# Monte Carlo (V365-006)
# ---------------------------------------------------------------------------

MC_RULES = ("C-MC-YEARS", "C-MC-PERCENTILES", "C-MC-MEDIAN-DRIFT")


@pytest.mark.parametrize("rule_id", MC_RULES)
@pytest.mark.parametrize("pid", [9101, 9103])
def test_mc_rules_pass_on_portfolio(repo, rule_id, pid):
    assert_status(run_rule(rule_id, portfolio_ctx(repo, pid), scope_of(pid)), "pass")


@pytest.mark.parametrize("rule_id", MC_RULES)
def test_mc_rules_pass_on_aggregate(repo, rule_id):
    ctx = aggregate_ctx(repo)
    outcome = run_rule(rule_id, ctx, AGG_SCOPE)
    assert_status(outcome, "pass")
    assert ("get_aggregate_monte_carlo", {"portfolio_ids": AGG_IDS}) in ctx.calls


@pytest.mark.parametrize("rule_id", MC_RULES)
def test_mc_rules_skip(repo, rule_id):
    assert_status(run_rule(rule_id, portfolio_ctx(repo, 9106), scope_of(9106)), "skip", "empty_portfolio")
    assert_status(run_rule(rule_id, portfolio_ctx(repo, 9107), scope_of(9107)), "skip", "no_history")


def test_mc_years_fails_without_year_ten(repo, monkeypatch):
    # V365-006: projections[:10] prima del filtro year > 0 → anni 1..9.
    monkeypatch.setattr(ct, "_MC_YEARS", range(1, 10))
    outcome = run_rule("C-MC-YEARS", portfolio_ctx(repo, 9101), scope_of(9101))
    assert_status(outcome, "fail", "invariant_violated")
    assert outcome["evidence"][0]["observed"] == list(range(1, 10))
    monkeypatch.setattr(ct, "_MC_YEARS", range(0, 10))  # anni 0..9
    assert_status(run_rule("C-MC-YEARS", aggregate_ctx(repo), AGG_SCOPE), "fail")


def test_mc_years_fails_on_undeclared_unit(repo):
    mc = tool("get_monte_carlo", repo, 9101)
    del mc["unit"], mc["initial_value"]
    assert_status(run_rule("C-MC-YEARS", portfolio_ctx(repo, 9101, {"get_monte_carlo": mc}), scope_of(9101)), "fail")


def test_mc_percentiles_fail_when_swapped(repo):
    mc = tool("get_monte_carlo", repo, 9101)
    for p in mc["projections"]:
        p["p25"], p["p50"] = p["p50"], p["p25"]
    outcome = run_rule("C-MC-PERCENTILES", portfolio_ctx(repo, 9101, {"get_monte_carlo": mc}), scope_of(9101))
    assert_status(outcome, "fail", "invariant_violated")
    assert len(outcome["evidence"]) == 10
    assert_status(run_rule("C-MC-PERCENTILES", aggregate_ctx(repo, mc), AGG_SCOPE), "fail")


def test_mc_median_drift_fails_on_euro_percentiles(repo):
    # V365-006 (unità non dichiarata): percentili in euro, p50 dell'anno 1 ≈ valore del portafoglio.
    mc = tool("get_monte_carlo", repo, 9101)
    value = sum(h["market_value"] for h in PORTFOLIOS[9101])
    for p in mc["projections"]:
        for k in ("p25", "p50", "p75"):
            p[k] = round(p[k] * value / 100, 1)
    outcome = run_rule("C-MC-MEDIAN-DRIFT", portfolio_ctx(repo, 9101, {"get_monte_carlo": mc}), scope_of(9101))
    assert_status(outcome, "fail", "invariant_violated")
    assert_status(run_rule("C-MC-MEDIAN-DRIFT", aggregate_ctx(repo, mc), AGG_SCOPE), "fail")


# ---------------------------------------------------------------------------
# C-DIV-CURRENCY (V-DIV-MIXED-CCY)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9104, 9105])
def test_dividend_currency_passes(repo, pid):
    assert_status(run_rule("C-DIV-CURRENCY", portfolio_ctx(repo, pid), scope_of(pid)), "pass")


def test_dividend_currency_mixed_output_shape(repo):
    ds = tool("get_dividend_summary", repo, 9104)
    assert ds["mixed_currencies"] is True and ds["total_dividends_received"] is None
    assert set(ds["dividends_by_currency"]) == {"EUR", "GBP"}


def test_dividend_currency_fails_on_single_total_over_currencies(repo):
    # V-DIV-MIXED-CCY: output di prima di TASK-44, un totale unico che somma GBP ed EUR.
    ds = tool("get_dividend_summary", repo, 9104)
    amounts = [t["quantity"] * t["price"] for t in TRANSACTIONS[9104]]
    for key in ("dividends_by_currency", "mixed_currencies", "dividends_currency", "currency_note"):
        ds.pop(key, None)
    ds["total_dividends_received"] = round(sum(amounts), 2)
    ds["dividends_last_12m"] = round(sum(amounts), 2)
    outcome = run_rule("C-DIV-CURRENCY", portfolio_ctx(repo, 9104, {"get_dividend_summary": ds}), scope_of(9104))
    assert_status(outcome, "fail", "invariant_violated")
    paths = {e["path"] for e in outcome["evidence"]}
    assert {"dividends_by_currency", "mixed_currencies", "total_dividends_received"} <= paths


def test_dividend_currency_fails_on_summed_total_with_flag(repo):
    ds = tool("get_dividend_summary", repo, 9104)
    ds["mixed_currencies"] = False
    ds["total_dividends_received"] = round(sum(t["quantity"] * t["price"] for t in TRANSACTIONS[9104]), 2)
    ds["dividends_currency"] = "EUR"
    assert_status(run_rule("C-DIV-CURRENCY", portfolio_ctx(repo, 9104, {"get_dividend_summary": ds}),
                           scope_of(9104)), "fail")


def test_dividend_currency_fails_on_count(repo):
    # V365-009: dividendi ripetuti / persi fra transazioni e riepilogo.
    ds = tool("get_dividend_summary", repo, 9105)
    ds["dividends_by_currency"]["EUR"]["count"] += 1
    ds["dividend_transactions_count"] += 1
    assert_status(run_rule("C-DIV-CURRENCY", portfolio_ctx(repo, 9105, {"get_dividend_summary": ds}),
                           scope_of(9105)), "fail")


def test_dividend_currency_skips_without_dividends(repo):
    assert_status(run_rule("C-DIV-CURRENCY", portfolio_ctx(repo, 9102), scope_of(9102)), "skip", "no_reference_data")
    assert_status(run_rule("C-DIV-CURRENCY", portfolio_ctx(repo, 9106), scope_of(9106)), "skip", "no_reference_data")


# ---------------------------------------------------------------------------
# Variazioni giornaliere (V365-005, V-DAYMOVERS-ROOT)
# ---------------------------------------------------------------------------


def _day_movers_5ffa5da(repo: StubRepo, pid: int) -> dict:
    """get_day_movers di 5ffa5da (prima di TASK-44): il day_change_pct 0.0 di default di una posizione
    senza chiusura precedente è trattato come variazione, nessun conteggio delle esclusioni."""
    positions = repo.get_positions(pid, USER)
    valid = [p for p in positions if not p.price_stale and p.price_date is not None]
    excluded = len(positions) - len(valid)
    if not valid:
        return {"best": None, "worst": None, "reason": "Nessuna posizione con prezzo aggiornato.",
                "valid_positions": 0, "excluded_stale": excluded}

    def mover(p):
        return {"symbol": p.symbol, "name": p.name, "day_change_pct": round(p.day_change_pct, 2),
                "price_date": p.price_date.isoformat()}

    best = min(valid, key=lambda p: (-p.day_change_pct, p.symbol))
    worst = min(valid, key=lambda p: (p.day_change_pct, p.symbol))
    return {"best": mover(best), "worst": mover(worst), "valid_positions": len(valid), "excluded_stale": excluded}


@pytest.mark.parametrize("rule_id", ["C-DAYMOVERS-NONZERO-INCLUDED", "C-DAYMOVERS-CONSISTENCY"])
@pytest.mark.parametrize("pid", [9101, 9107])
def test_daymovers_rules_pass(repo, rule_id, pid):
    assert_status(run_rule(rule_id, portfolio_ctx(repo, pid), scope_of(pid)), "pass")


def test_daymovers_9107_output_shape(repo):
    dm = tool("get_day_movers", repo, 9107)
    assert dm["valid_positions"] == 1 and dm["best"]["symbol"] == dm["worst"]["symbol"] == "AUDEQ.MI"
    assert dm["excluded_stale"] == 1 and dm["excluded_no_previous_close"] == 1
    rows = {r["symbol"]: r for r in tool("get_positions", repo, 9107)["positions"]}
    assert rows["AUDNPC.MI"]["day_change_pct"] == 0 and not rows["AUDNPC.MI"]["price_stale"]


def test_daymovers_nonzero_fails_on_target_returns_source(repo):
    # V365-005 / V-DAYMOVERS-ROOT: fonte sbagliata (rendimenti a 1 anno dei target) → {"best": null, "worst": null}.
    outcome = run_rule("C-DAYMOVERS-NONZERO-INCLUDED",
                       portfolio_ctx(repo, 9101, {"get_day_movers": {"best": None, "worst": None}}), scope_of(9101))
    assert_status(outcome, "fail", "invariant_violated")
    assert_status(run_rule("C-DAYMOVERS-CONSISTENCY",
                           portfolio_ctx(repo, 9101, {"get_day_movers": {"best": None, "worst": None}}),
                           scope_of(9101)), "fail")


def test_daymovers_nonzero_fails_on_wrong_extremes(repo):
    dm = tool("get_day_movers", repo, 9101)
    dm["best"] = {"symbol": "AUDEQ.MI", "name": "x", "day_change_pct": 0.85, "price_date": TODAY.isoformat()}
    outcome = run_rule("C-DAYMOVERS-NONZERO-INCLUDED", portfolio_ctx(repo, 9101, {"get_day_movers": dm}),
                       scope_of(9101))
    assert_status(outcome, "fail")
    assert any(e["path"] == "positions[symbol=AUDTECH.DE].day_change_pct" for e in outcome["evidence"])


def test_daymovers_consistency_fails_on_default_zero_as_change(repo):
    # V-DAYMOVERS-ROOT: 0.0 di default trattato come variazione (AUDNPC.MI «peggiore» a 0%), output di 5ffa5da.
    dm = sanitize_output(_day_movers_5ffa5da(repo, 9107))
    assert dm["worst"]["symbol"] == "AUDNPC.MI" and dm["worst"]["day_change_pct"] == 0.0
    outcome = run_rule("C-DAYMOVERS-CONSISTENCY", portfolio_ctx(repo, 9107, {"get_day_movers": dm}), scope_of(9107))
    assert_status(outcome, "fail", "invariant_violated")
    assert any(e["path"] == "excluded_no_previous_close" for e in outcome["evidence"])


def test_daymovers_consistency_fails_on_stale_mover(repo):
    dm = tool("get_day_movers", repo, 9107)
    dm["worst"] = {"symbol": "AUDSTL.MI", "name": "x", "day_change_pct": 0.0, "price_date": None}
    dm["valid_positions"], dm["excluded_stale"] = 2, 0
    outcome = run_rule("C-DAYMOVERS-CONSISTENCY", portfolio_ctx(repo, 9107, {"get_day_movers": dm}), scope_of(9107))
    assert_status(outcome, "fail")
    paths = {e["path"] for e in outcome["evidence"]}
    assert {"worst.symbol", "positions[symbol=AUDSTL.MI].price_stale"} <= paths


def test_daymovers_skips(repo):
    for rule_id in ("C-DAYMOVERS-NONZERO-INCLUDED", "C-DAYMOVERS-CONSISTENCY"):
        assert_status(run_rule(rule_id, portfolio_ctx(repo, 9106), scope_of(9106)), "skip", "empty_portfolio")
    # Mercato chiuso / giornata piatta: nessuna variazione non nulla.
    flat = StubRepo({9301: [holding("AUDEQ.MI", 1000.0), holding("AUDBD.MI", 500.0, previous_close=False)]},
                    {9301: []})
    ctx = FakeAuditContext([
        ("get_positions", {"portfolio_id": 9301}, tool("get_positions", flat, 9301)),
        ("get_day_movers", {"portfolio_id": 9301}, tool("get_day_movers", flat, 9301)),
    ])
    assert_status(run_rule("C-DAYMOVERS-NONZERO-INCLUDED", ctx, scope_of(9301)), "skip", "no_reference_data")
    assert_status(run_rule("C-DAYMOVERS-CONSISTENCY", ctx, scope_of(9301)), "pass")


# ---------------------------------------------------------------------------
# Denominatore della variazione giornaliera del riepilogo (S-2026-11-11-03, TASK-86)
# ---------------------------------------------------------------------------


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _BarsConn:
    """Le tre letture di _summary_from_positions: barre giornaliere, tick (nessuno), cambi (nessuno)."""

    def __init__(self, bars):
        self.bars = bars

    def execute(self, statement, _params):
        sql = " ".join(str(statement).split())
        if "ranked_daily" in sql:
            return _Rows(self.bars)
        return _Rows([])

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _bars_of(stub: StubRepo, pid: int) -> list[dict]:
    """Barre coerenti con le posizioni finte (prezzo 100): oggi e ieri per una variazione, due barre
    vecchie e uguali per una quotazione ferma, una sola barra senza chiusura precedente."""
    bars = []
    for h in stub._portfolios[pid]:
        aid = SYMBOL_ID[h["symbol"]]
        if h["stale"]:
            day = h["price_date"]
            bars += [{"asset_id": aid, "price_date": day, "close": 100.0, "rn": 1},
                     {"asset_id": aid, "price_date": day - timedelta(days=1), "close": 100.0, "rn": 2}]
        elif not h["previous_close"]:
            bars.append({"asset_id": aid, "price_date": TODAY, "close": 100.0, "rn": 1})
        else:
            bars += [{"asset_id": aid, "price_date": TODAY, "close": 100.0, "rn": 1},
                     {"asset_id": aid, "price_date": YESTERDAY, "close": 100.0 / (1 + h["day_change_pct"] / 100.0),
                      "rn": 2}]
    return bars


def _real_summary(stub: StubRepo, pid: int):
    """PortfolioSummary del vero SummaryMixin (app/repository/_summary.py) sulle barre del portafoglio finto."""
    from app.repository._base import AssetMeta
    from app.repository._summary import SummaryMixin

    conn = _BarsConn(_bars_of(stub, pid))

    class _SummaryRepo(SummaryMixin):
        engine = SimpleNamespace(begin=lambda: conn)

        def _get_asset_meta(self, _conn, asset_ids):
            return {aid: AssetMeta(symbol=ASSETS[aid]["symbol"], quote_currency="EUR") for aid in asset_ids}

    return _SummaryRepo()._summary_from_positions(pid, "EUR", stub.get_positions(pid, USER), 0.0)


def daychange_ctx(stub: StubRepo, pid: int, summary_override: dict | None = None) -> FakeAuditContext:
    summary_obj = _real_summary(stub, pid)
    summary_repo = SimpleNamespace(get_summary=lambda _pid, _uid: summary_obj)
    summary = summary_override or sanitize_output(
        ct._TOOL_HANDLERS["get_portfolio_summary"]({}, summary_repo, None, pid, USER))
    args = {"portfolio_id": pid}
    responses = [("get_positions", args, tool("get_positions", stub, pid)),
                 ("get_portfolio_summary", args, summary)]
    for p in stub.get_positions(pid, USER):
        responses.append(("search_asset_info", {"portfolio_id": pid, "symbol": p.symbol},
                          tool("search_asset_info", stub, pid, {"symbol": p.symbol})))
    return FakeAuditContext(responses)


@pytest.mark.parametrize("pid", [9101, 9107])
def test_daychange_denominator_passes_on_the_real_summary(repo, pid):
    # Sul codice prima di TASK-86 (AUDNPC.MI fuori dal denominatore) 9107 dà fail: 0,51 contro 0,42.
    outcome = run_rule("C-DAYCHANGE-DENOMINATOR", daychange_ctx(repo, pid), scope_of(pid))
    assert_status(outcome, "pass")


def test_daychange_denominator_9107_counts_every_position(repo):
    # AUDEQ.MI 3.000 (+0,8512%), AUDSTL.MI 2.000 ferma, AUDNPC.MI 1.000 senza chiusura precedente.
    summary = _real_summary(repo, 9107)
    previous_eq = 3000.0 / 1.008512
    assert summary.day_change == round(3000.0 - previous_eq, 2)
    assert summary.day_change_pct == round((3000.0 - previous_eq) / (previous_eq + 3000.0) * 100.0, 2)


def test_daychange_denominator_fails_when_no_previous_close_leaves_the_denominator(repo):
    # Difetto di S-2026-11-11-03 (codice prima di TASK-86): AUDNPC.MI esce dal ciclo con `continue` prima di
    # previous_market_value, la percentuale è calcolata su 3.000/1,008512 + 2.000 invece che anche su 1.000.
    ctx_ok = daychange_ctx(repo, 9107)
    summary = copy.deepcopy(ctx_ok.call("get_portfolio_summary", {"portfolio_id": 9107}))
    previous_without_npc = 3000.0 / 1.008512 + 2000.0
    summary["day_change_pct"] = round(summary["day_change"] / previous_without_npc * 100.0, 2)
    outcome = run_rule("C-DAYCHANGE-DENOMINATOR", daychange_ctx(repo, 9107, summary), scope_of(9107))
    assert_status(outcome, "fail", "invariant_violated")
    assert outcome["evidence"][0]["path"] == "day_change_pct"


def test_daychange_denominator_skips(repo):
    assert_status(run_rule("C-DAYCHANGE-DENOMINATOR", daychange_ctx(repo, 9106), scope_of(9106)),
                  "skip", "empty_portfolio")
    # 9104: AUDUS.L in USD, AUDUK.L in GBP → la variazione della posizione non include il cambio.
    outcome = run_rule("C-DAYCHANGE-DENOMINATOR", daychange_ctx(repo, 9104), scope_of(9104))
    assert_status(outcome, "skip", "not_applicable")
    assert {e["args"]["symbol"] for e in outcome["evidence"]} == {"AUDUS.L", "AUDUK.L"}
    # Giornata piatta: nessuna variazione.
    flat = StubRepo({9301: [holding("AUDEQ.MI", 1000.0), holding("AUDBD.MI", 500.0, previous_close=False)]},
                    {9301: []})
    assert_status(run_rule("C-DAYCHANGE-DENOMINATOR", daychange_ctx(flat, 9301), scope_of(9301)),
                  "skip", "no_reference_data")


def test_tool_errors_propagate(repo):
    ctx = FakeAuditContext([("get_cost_breakdown", {"portfolio_id": 9101}, RuntimeError("db giù"))])
    with pytest.raises(FakeToolError):
        run_rule("C-TER-RANGE", ctx, scope_of(9101))
