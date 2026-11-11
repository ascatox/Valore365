"""TASK-78: portafogli di prova dell'Auditor su un PostgreSQL 16 reale (cluster usa e getta).

Applica ``database/schema.sql``, tutte le migrazioni e ``scripts/auditor/audit_seed.sql`` in un
database dedicato del cluster della fixture ``pg_engine`` (così il seed non tocca i dati degli
altri test), poi verifica:

- struttura del seed (portafogli 9101-9107, 13 strumenti ``AUD*``, schede, prezzi, cambi), come
  da ``docs/auditor/rules.md`` §1;
- i valori documentati in ``scripts/auditor/README.md``, letti con i tool MCP veri
  (``run_tool_sync``) e un finance client offline (architettura §5.5);
- per ogni regola del catalogo, che il portafoglio di prova indicato soddisfi la precondizione
  per non andare in ``skip``, e alcune invarianti che le regole controlleranno sul codice corretto.

Saltato quando i binari di Postgres mancano (vedi conftest.py).
"""

from __future__ import annotations

import itertools
import math
import socket
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.mcp_server.tools import ToolDependencies, run_tool_sync, sanitize_output
from app.repository import PortfolioRepository
from app.services.performance_audit import build_performance_audit_export
from app.services.performance_service import PerformanceService

REPO_ROOT = Path(__file__).resolve().parents[4]
DATABASE_DIR = REPO_ROOT / "database"
SEED = REPO_ROOT / "scripts" / "auditor" / "audit_seed.sql"
DB_NAME = "auditor_seed"
USER = "auditor-seed-user"
PORTFOLIO_IDS = [9101, 9102, 9103, 9104, 9105, 9106, 9107]
NON_EMPTY = [9101, 9102, 9103, 9104, 9105, 9107]

# rules.md §1: simbolo -> (id, tipo salvato, valuta di quotazione, classe attesa, instrument_type)
INSTRUMENTS = {
    "AUDEQ.MI": (9101, "etf", "EUR", "equity", "etf"),
    "AUDBD.MI": (9102, "etf", "EUR", "bond", "etf"),
    "AUDTECH.DE": (9103, "etf", "EUR", "equity", "etf"),
    "AUDGOV.MI": (9104, "etf", "EUR", "bond", "etf"),
    "AUDHY.DE": (9105, "stock", "EUR", "bond", "etf"),
    "AUDBTP": (9106, "bond", "EUR", "bond", "bond"),
    "AUDGLD.DE": (9107, "stock", "EUR", "gold", "etc"),
    "AUDCMD.MI": (9108, "etf", "EUR", "commodity", "etf"),
    "AUDTHM.DE": (9109, "etf", "EUR", "unknown", "etf"),
    "AUDUS.L": (9110, "etf", "USD", "equity", "etf"),
    "AUDUK.L": (9111, "etf", "GBP", "bond", "etf"),
    "AUDSTL.MI": (9112, "etf", "EUR", "equity", "etf"),
    "AUDNPC.MI": (9113, "etf", "EUR", "equity", "etf"),
}

PORTFOLIO_NAMES = {
    9101: "AUD Bilanciato storico",
    9102: "AUD Solo obbligazioni",
    9103: "AUD Oro e materie prime",
    9104: "AUD Londra e valute",
    9105: "AUD Import",
    9106: "AUD Vuoto",
    9107: "AUD Quotazioni ferme",
}

# Valori documentati (scripts/auditor/README.md): market_value, cash_balance e posizioni
# (simbolo -> quantità, prezzo in EUR, valore, peso).
DOCUMENTED = {
    9101: (100000.00, 9256.50, {
        "AUDEQ.MI": (700, 100.0, 70000.00, 70.0),
        "AUDBD.MI": (400, 50.0, 20000.00, 20.0),
        "AUDTECH.DE": (50, 200.0, 10000.00, 10.0),
    }),
    9102: (42350.00, 8144.00, {
        "AUDGOV.MI": (150, 120.0, 18000.00, 42.5),
        "AUDHY.DE": (150, 95.0, 14250.00, 33.65),
        "AUDBTP": (100, 101.0, 10100.00, 23.85),
    }),
    9103: (40000.00, 2492.00, {
        "AUDGLD.DE": (400, 40.0, 16000.00, 40.0),
        "AUDEQ.MI": (100, 100.0, 10000.00, 25.0),
        "AUDCMD.MI": (400, 20.0, 8000.00, 20.0),
        "AUDTHM.DE": (200, 30.0, 6000.00, 15.0),
    }),
    9104: (27480.00, 3705.97, {
        "AUDUS.L": (100, 101.2, 10120.00, 36.83),
        "AUDUK.L": (800, 11.7, 9360.00, 34.06),
        "AUDEQ.MI": (80, 100.0, 8000.00, 29.11),
    }),
    9105: (15000.00, 5545.00, {
        "AUDEQ.MI": (100, 100.0, 10000.00, 66.67),
        "AUDBD.MI": (100, 50.0, 5000.00, 33.33),
    }),
    9106: (0.0, 0.0, {}),
    9107: (16000.00, 4047.00, {
        "AUDSTL.MI": (100, 60.0, 6000.00, 37.5),
        "AUDEQ.MI": (50, 100.0, 5000.00, 31.25),
        "AUDNPC.MI": (200, 25.0, 5000.00, 31.25),
    }),
}

HISTORICAL_WINDOWS = {
    "Global Financial Crisis": (date(2007, 10, 1), date(2009, 3, 31)),
    "Dot-Com Crash": (date(2000, 3, 1), date(2002, 10, 31)),
    "Covid Crash": (date(2020, 2, 19), date(2020, 3, 23)),
    "Bear Market 2022": (date(2022, 1, 3), date(2022, 10, 12)),
}
# Impatti storici di 9101 (metodo historical, copertura 100%).
IMPACTS_9101 = {"Global Financial Crisis": -35.7, "Dot-Com Crash": -32.6, "Covid Crash": -23.9, "Bear Market 2022": -20.0}

ALL_ARGS_REBALANCE = ({"mode": "rebalance"}, {"mode": "buy_only", "available_cash": 1000.0}, {"mode": "sell_only"})
CASH_SIDES = {"deposit", "withdrawal", "dividend", "fee", "interest"}


class OfflineFinanceClient:
    """Finance client dell'Auditor (architettura §5.5): ogni chiamata fallisce, nessuna rete."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)

        def _offline(*_args, **_kwargs):
            self.calls.append(name)
            raise RuntimeError(f"auditor offline: {name}")

        return _offline


def _psql_base(pg_engine) -> list[str]:
    url = pg_engine.url
    host = url.query["host"]
    port = str(url.query.get("port") or url.port)
    return ["psql", "-q", "-h", host, "-p", port, "-U", "postgres", "-v", "ON_ERROR_STOP=1"]


def _apply(psql: list[str], path: Path) -> None:
    subprocess.run([*psql, "-d", DB_NAME, "-f", str(path)], check=True, capture_output=True, text=True, cwd="/")


@pytest.fixture(scope="module")
def seed_db(pg_engine):
    psql = _psql_base(pg_engine)
    subprocess.run([*psql, "-d", "postgres", "-c", f"drop database if exists {DB_NAME}"], check=True,
                   capture_output=True, text=True, cwd="/")
    subprocess.run([*psql, "-d", "postgres", "-c", f"create database {DB_NAME}"], check=True,
                   capture_output=True, text=True, cwd="/")
    _apply(psql, DATABASE_DIR / "schema.sql")
    for migration in sorted((DATABASE_DIR / "migrations").glob("*.sql")):
        _apply(psql, migration)
    _apply(psql, SEED)
    url = pg_engine.url
    engine = create_engine(
        f"postgresql+psycopg://postgres@/{DB_NAME}?host={url.query['host']}&port={url.query.get('port') or url.port}",
        pool_size=3, max_overflow=3,
    )
    yield {"engine": engine, "psql": psql}
    engine.dispose()
    subprocess.run([*psql, "-d", "postgres", "-c", f"drop database if exists {DB_NAME}"], capture_output=True, cwd="/")


@pytest.fixture(scope="module")
def tools(seed_db):
    """run_tool_sync sul DB del seed, con le dipendenze del server MCP e il client offline."""
    import app.services.doctor_policy.service as doctor_service

    engine = seed_db["engine"]
    repo = PortfolioRepository(engine)
    finance = OfflineFinanceClient()
    deps = ToolDependencies(repo=repo, performance_service=PerformanceService(repo), finance_client=finance)
    patcher = pytest.MonkeyPatch()
    # I tool del Doctor usano il servizio di processo legato al repository di app.main
    # (DATABASE_URL dell'app): qui va legato al DB del seed (vedi architecture.md, Deviazioni TASK-78).
    patcher.setattr(doctor_service, "_default_service", doctor_service.DoctorPolicyService(repo))

    real_connect = socket.socket.connect

    def _no_network(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError(f"rete non ammessa durante l'audit: {address!r}")
        return real_connect(sock, address)

    patcher.setattr(socket.socket, "connect", _no_network)
    memo: dict[str, dict] = {}

    def call(tool: str, args: dict) -> dict:
        key = f"{tool}:{sorted(args.items())!r}"
        if key not in memo:
            memo[key] = sanitize_output(run_tool_sync(deps, tool, dict(args), USER))
        return memo[key]

    def try_call(tool: str, args: dict) -> dict:
        try:
            return {"ok": True, "result": call(tool, args), "error": None}
        except Exception as exc:  # McpToolError
            return {"ok": False, "result": None, "error": str(exc)}

    def performance_audit(pid: int) -> dict:
        return sanitize_output(build_performance_audit_export(
            deps.performance_service, pid, USER, period="1y", max_flows=200, offset=0,
        ))

    yield type("Tools", (), {
        "call": staticmethod(call), "try_call": staticmethod(try_call), "repo": repo, "deps": deps,
        "finance": finance, "engine": engine, "performance_audit": staticmethod(performance_audit),
    })
    patcher.undo()


def _rows(engine, sql: str, **params) -> list[dict]:
    with engine.begin() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _scalar(engine, sql: str, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _positions(tools, pid: int) -> list[dict]:
    return tools.call("get_positions", {"portfolio_id": pid})["positions"]


def _stress(tools, pid: int) -> dict:
    return {s["scenario_name"]: s for s in tools.call("get_stress_test", {"portfolio_id": pid})["scenarios"]}


def _info(tools, pid: int, symbol: str) -> dict:
    return tools.call("search_asset_info", {"portfolio_id": pid, "symbol": symbol})


def _close(a: float | None, b: float, tol: float = 0.005) -> bool:
    return a is not None and abs(float(a) - b) <= tol + 1e-9


# ---------------------------------------------------------------------------
# Struttura del seed
# ---------------------------------------------------------------------------


def test_portfolios_and_instruments_exist(seed_db):
    engine = seed_db["engine"]
    rows = _rows(engine, "select id, name, base_currency, cash_balance::float8 as cash from portfolios "
                         "where owner_user_id = :u order by id", u=USER)
    assert [r["id"] for r in rows] == PORTFOLIO_IDS
    assert {r["id"]: r["name"] for r in rows} == PORTFOLIO_NAMES
    assert all(r["base_currency"] == "EUR" and r["cash"] == 0 for r in rows)

    assets = {r["symbol"]: r for r in _rows(engine, "select id, symbol, asset_type, quote_currency from assets "
                                                     "where id between 9101 and 9113")}
    assert set(assets) == set(INSTRUMENTS)
    for symbol, (aid, asset_type, ccy, _cls, _itype) in INSTRUMENTS.items():
        assert (assets[symbol]["id"], assets[symbol]["asset_type"], assets[symbol]["quote_currency"]) == (aid, asset_type, ccy)
    # Nessun simbolo reale: la classificazione dipende solo dai dati del seed.
    assert all(s.startswith("AUD") for s in assets)


def test_reference_data_is_in_the_seed(seed_db):
    engine = seed_db["engine"]
    ter = {r["asset_id"]: float(r["ter"]) for r in _rows(engine, "select asset_id, ter from etf_enrichment where asset_id between 9101 and 9113")}
    assert ter == {9101: 0.22, 9102: 0.10, 9103: 0.30, 9104: 0.15, 9107: 0.25, 9108: 0.19,
                   9110: 0.20, 9111: 0.07, 9112: 0.12, 9113: 0.18}
    meta = {r["asset_id"]: r for r in _rows(engine, "select asset_id, expense_ratio::float8 as er, category, "
                                                     "dividend_yield::float8 as dy from asset_metadata where asset_id between 9101 and 9113")}
    assert {k: v["dy"] for k, v in meta.items()} == {9103: 0.6, 9104: 2.5, 9105: 5.0, 9106: 1.6, 9111: 3.0}
    assert meta[9105]["er"] == 0.005 and meta[9105]["category"] == "High Yield Bond"
    assert 9109 not in ter and 9109 not in meta  # AUDTHM.DE: nessun dato
    weights = _scalar(engine, "select country_weights from etf_enrichment where asset_id = 9101")
    assert sum(w["percentage"] for w in weights) == pytest.approx(100.0)
    targets = _rows(engine, "select portfolio_id, asset_id, weight_pct::float8 as w from portfolio_target_allocations "
                            "where portfolio_id between 9101 and 9107 order by asset_id")
    assert [(t["portfolio_id"], t["asset_id"], t["w"]) for t in targets] == [(9101, 9101, 50.0), (9101, 9102, 40.0), (9101, 9103, 10.0)]
    batch = _rows(engine, "select portfolio_id, status from csv_import_batches where owner_user_id = :u", u=USER)
    assert batch == [{"portfolio_id": 9105, "status": "committed"}]
    assert _scalar(engine, "select count(*) from transactions where portfolio_id = 9106") == 0


def test_price_history_covers_the_stress_windows_only_for_9101(seed_db):
    engine = seed_db["engine"]
    for start, end in HISTORICAL_WINDOWS.values():
        counts = {r["asset_id"]: r["n"] for r in _rows(
            engine, "select asset_id, count(*) as n from price_bars_1d where asset_id between 9101 and 9113 "
                    "and price_date between :s and :e group by asset_id", s=start, e=end)}
        assert set(counts) == {9101, 9102, 9103}  # strumenti di 9101
        assert all(n >= 2 for n in counts.values())
    # 9101: barre giornaliere per gli ultimi 400 giorni, oggi e ieri diverse.
    for aid in (9101, 9102, 9103):
        n = _scalar(engine, "select count(*) from price_bars_1d where asset_id = :a and price_date > current_date - 401", a=aid)
        assert n == 401
        today, yesterday = (r["close"] for r in _rows(
            engine, "select close::float8 as close from price_bars_1d where asset_id = :a "
                    "and price_date >= current_date - 1 order by price_date desc", a=aid))
        assert today != yesterday
    # 9102: solo gli ultimi 30 giorni.
    for aid in (9104, 9105, 9106):
        first = _scalar(engine, "select min(price_date) from price_bars_1d where asset_id = :a", a=aid)
        assert first == _scalar(engine, "select current_date - 30")
    # 9107: AUDSTL.MI fermo da 30 giorni, AUDNPC.MI una sola barra (oggi) e nessun tick.
    assert _scalar(engine, "select max(price_date) = current_date - 30 from price_bars_1d where asset_id = 9112")
    assert _rows(engine, "select price_date = current_date as today from price_bars_1d where asset_id = 9113") == [{"today": True}]
    assert _scalar(engine, "select count(*) from price_ticks where asset_id between 9101 and 9113") == 0


def test_fx_rates_cover_transactions_and_prices_of_9104(seed_db):
    engine = seed_db["engine"]
    for ccy in ("USD", "GBP"):
        missing = _scalar(engine, """
            select count(*) from generate_series(0, 400) as g(n)
            where not exists (select 1 from fx_rates_1d f where f.from_ccy = :c and f.to_ccy = 'EUR'
                              and f.price_date = current_date - g.n)""", c=ccy)
        assert missing == 0
    oldest_tx = _scalar(engine, "select min(trade_at)::date from transactions where portfolio_id = 9104")
    assert oldest_tx >= _scalar(engine, "select current_date - 400")


def test_seed_can_be_reapplied(seed_db):
    engine = seed_db["engine"]

    def counts():
        return _rows(engine, """
            select (select count(*) from portfolios where owner_user_id = 'auditor-seed-user') as p,
                   (select count(*) from transactions where owner_user_id = 'auditor-seed-user') as t,
                   (select count(*) from price_bars_1d where asset_id between 9101 and 9113) as b,
                   (select count(*) from fx_rates_1d where provider = 'auditor-seed') as f,
                   (select count(*) from etf_enrichment where asset_id between 9101 and 9113) as e""")[0]

    before = counts()
    _apply(seed_db["psql"], SEED)
    assert counts() == before


# ---------------------------------------------------------------------------
# Valori documentati, letti con i tool MCP
# ---------------------------------------------------------------------------


def test_list_portfolios_returns_the_seed(tools):
    portfolios = tools.call("list_portfolios", {})["portfolios"]
    assert sorted(p["id"] for p in portfolios) == PORTFOLIO_IDS
    assert {p["base_currency"] for p in portfolios} == {"EUR"}


@pytest.mark.parametrize("pid", PORTFOLIO_IDS)
def test_documented_values(tools, pid):
    market_value, cash, positions = DOCUMENTED[pid]
    summary = tools.call("get_portfolio_summary", {"portfolio_id": pid})
    assert _close(summary["market_value"], market_value, 0.0)
    assert _close(summary["cash_balance"], cash, 0.0)
    assert _close(tools.call("get_cash_balance", {"portfolio_id": pid})["total_cash"], cash, 0.0)
    rows = {r["symbol"]: r for r in _positions(tools, pid)}
    assert set(rows) == set(positions)
    for symbol, (qty, price, value, weight) in positions.items():
        row = rows[symbol]
        assert (row["quantity"], row["market_price"], row["market_value"], row["weight"]) == (qty, price, value, weight), symbol
        assert row["price_fallback"] is None and row["fx_missing"] is False


def test_aggregate_view(tools):
    agg = tools.call("get_aggregate_summary", {"portfolio_ids": PORTFOLIO_IDS})
    assert agg["portfolio_ids"] == PORTFOLIO_IDS
    assert _close(agg["market_value"], sum(v[0] for v in DOCUMENTED.values()), 0.0)
    assert _close(agg["cash_balance"], sum(v[1] for v in DOCUMENTED.values()), 0.011)
    positions = tools.call("get_aggregate_positions", {"portfolio_ids": PORTFOLIO_IDS})
    assert positions["positions_count"] == 13
    eq = next(r for r in positions["positions"] if r["symbol"] == "AUDEQ.MI")
    assert eq["quantity"] == 700 + 100 + 80 + 100 + 50  # AUDEQ.MI in cinque portafogli


@pytest.mark.parametrize("symbol", sorted(INSTRUMENTS))
def test_instrument_classification(tools, symbol):
    pid = next(p for p, (_mv, _c, pos) in DOCUMENTED.items() if symbol in pos)
    _aid, asset_type, ccy, asset_class, instrument_type = INSTRUMENTS[symbol]
    info = _info(tools, pid, symbol)
    assert info["match"] == "portfolio" and not info.get("warning")
    assert info["symbol"].upper() == symbol.upper()
    assert (info["type"], info["asset_class"], info["instrument_type"], info["currency"]) == (
        asset_type, asset_class, instrument_type, ccy)


def test_offline_client_only_used_by_xray(tools):
    tools.call("get_xray_summary", {"portfolio_id": 9101})
    assert set(tools.finance.calls) <= {"get_etf_top_holdings"}


# ---------------------------------------------------------------------------
# Gruppo A — stress test e classificazione
# ---------------------------------------------------------------------------


def test_stress_methods_historical_for_9101_proxy_for_9102_and_9103(tools):
    s9101 = _stress(tools, 9101)
    for name, impact in IMPACTS_9101.items():
        assert (s9101[name]["method"], s9101[name]["coverage_pct"]) == ("historical", 100.0)
        assert s9101[name]["estimated_portfolio_impact_pct"] == impact
    for pid in (9102, 9103):
        scen = _stress(tools, pid)
        for name in HISTORICAL_WINDOWS:
            assert scen[name]["method"] == "proxy"
            assert "class_proxy_drawdowns" in scen[name]["flags"]
            assert all(r["source"] == "proxy" for r in scen[name]["class_breakdown"])
    assert {_stress(tools, 9102)[n]["coverage_pct"] for n in HISTORICAL_WINDOWS} == {0.0}
    assert {_stress(tools, 9103)[n]["coverage_pct"] for n in HISTORICAL_WINDOWS} == {25.0}  # solo AUDEQ.MI ha storico
    agg = {s["scenario_name"]: s for s in tools.call("get_aggregate_stress_test", {"portfolio_ids": PORTFOLIO_IDS})["scenarios"]}
    assert {agg[n]["method"] for n in HISTORICAL_WINDOWS} == {"proxy"}


def test_stress_historical_scenarios_distinct_between_portfolios(tools):
    """Precondizione e invariante di A-STRESS-HIST-DISTINCT sullo scope user."""
    vectors, impacts = {}, {}
    for pid in PORTFOLIO_IDS:
        scen = _stress(tools, pid)
        hist = [s for s in scen.values() if s["scenario_type"] == "historical" and s["method"] != "not_available"]
        if not hist:
            continue
        vectors[pid] = {r["asset_class"]: r["weight_pct"] for r in scen["Global Equity Crash"]["class_breakdown"]}
        impacts[pid] = {s["scenario_name"]: s["estimated_portfolio_impact_pct"] for s in hist}
    assert {9101, 9102, 9103} <= set(vectors)
    for p, q in itertools.combinations(sorted(vectors), 2):
        classes = set(vectors[p]) | set(vectors[q])
        distance = sum(abs(vectors[p].get(c, 0) - vectors[q].get(c, 0)) for c in classes)
        if distance > 1.0:
            assert not all(abs(impacts[p][n] - impacts[q][n]) <= 0.01 for n in HISTORICAL_WINDOWS), (p, q)


def test_stress_shock_classes_and_unknown_flag(tools):
    s9103 = _stress(tools, 9103)
    crash = s9103["Global Equity Crash"]
    assert {r["asset_class"]: r["weight_pct"] for r in crash["class_breakdown"]} == {
        "gold": 40.0, "equity": 25.0, "commodity": 20.0, "unknown": 15.0}
    for s in s9103.values():
        if s["scenario_type"] == "shock":
            assert "unknown_asset_class_equity_shock" in s["flags"]
    s9102 = _stress(tools, 9102)
    assert {r["asset_class"] for r in s9102["Global Equity Crash"]["class_breakdown"]} == {"bond"}
    tech = _stress(tools, 9101)["US Tech Crash"]["most_impacted"]
    assert {m["symbol"]: m["loss_pct"] for m in tech}["AUDTECH.DE"] == -45.0  # moltiplicatore tech 1,5


@pytest.mark.parametrize("pid", [9101, 9102, 9103])
def test_stress_classes_match_instrument_sheet(tools, pid):
    """A-CLASS-STRESS-CONSISTENT: stesse classi e pesi in scheda e stress test."""
    by_sheet: dict[str, float] = {}
    for row in _positions(tools, pid):
        cls = _info(tools, pid, row["symbol"])["asset_class"]
        by_sheet[cls] = by_sheet.get(cls, 0.0) + row["weight"]
    crash = _stress(tools, pid)["Global Equity Crash"]
    by_stress = {r["asset_class"]: r["weight_pct"] for r in crash["class_breakdown"]}
    assert set(by_sheet) == set(by_stress)
    assert all(abs(by_sheet[c] - by_stress[c]) <= 0.02 for c in by_sheet)


# ---------------------------------------------------------------------------
# Gruppo B — ribilanciamento, PAC, simulazioni (9101)
# ---------------------------------------------------------------------------


def test_rebalance_needs_sells_to_fund_buys(tools):
    results = [tools.call("calculate_rebalance_orders", {"portfolio_id": 9101, **a}) for a in ALL_ARGS_REBALANCE]
    rebalance, buy_only, sell_only = results
    for r in results:
        totals = r["totals"]
        assert totals["invariant_ok"] is True
        assert abs(totals["cash_after"] - (totals["cash_before"] + totals["extra_cash"] + totals["sells_eur"] - totals["buys_eur"])) <= 0.01
        assert totals["cash_after"] >= -0.01
    sides = {o["symbol"]: o["side"] for o in rebalance["orders"]}
    assert sides["AUDEQ.MI"] == "sell" and sides["AUDBD.MI"] == "buy"
    assert rebalance["totals"]["buys_eur"] > rebalance["totals"]["cash_before"]  # la liquidità da sola non basta
    assert buy_only["totals"]["extra_cash"] == 1000.0 and buy_only["totals"]["sells_eur"] == 0
    assert all(o["side"] == "buy" for o in buy_only["orders"])
    assert all(o["side"] == "sell" for o in sell_only["orders"]) and sell_only["totals"]["buys_eur"] == 0
    assert tools.call("calculate_rebalance_orders", {"portfolio_id": 9102, "mode": "rebalance"}).get("totals") is None


def test_pac_and_what_if(tools):
    pac = tools.call("calculate_pac_contribution", {"portfolio_id": 9101, "monthly_amount": 500.0})
    assert pac["total_allocated"] == 500.0 and pac["distribution"]
    assert abs(sum(d["amount_eur"] for d in pac["distribution"]) - 500.0) <= 0.01
    first = _positions(tools, 9101)[0]
    assert first["symbol"] == "AUDEQ.MI"
    v = first["market_value"]
    buy = tools.call("calculate_what_if", {"portfolio_id": 9101, "action": "buy", "symbol": "AUDEQ.MI", "amount_eur": 1000.0})
    assert abs(buy["new_weight"] - (70000 + 1000) / 101000 * 100) <= 0.02
    sell = tools.call("calculate_what_if", {"portfolio_id": 9101, "action": "sell", "symbol": "AUDEQ.MI", "amount_eur": round(v / 2, 2)})
    assert abs(sell["new_weight"] - (70000 - 35000) / 65000 * 100) <= 0.02
    over = tools.try_call("calculate_what_if", {"portfolio_id": 9101, "action": "sell", "symbol": "AUDEQ.MI",
                                                "amount_eur": round(v + 1000.0, 2)})
    assert over["ok"] is False


# ---------------------------------------------------------------------------
# Gruppo C — costi, reddito, dividendi, Monte Carlo, variazioni
# ---------------------------------------------------------------------------


def test_costs(tools):
    c9101 = tools.call("get_cost_breakdown", {"portfolio_id": 9101})
    assert (c9101["weighted_ter_pct"], c9101["ter_coverage_pct"], c9101["missing_ter_symbols"]) == (0.204, 100.0, [])
    assert c9101["estimated_annual_cost_known_eur"] == 204.0
    c9102 = {r["symbol"]: r for r in tools.call("get_cost_breakdown", {"portfolio_id": 9102})["position_costs"]}
    assert (c9102["AUDHY.DE"]["ter_pct"], c9102["AUDHY.DE"]["ter_source"]) == (0.5, "yfinance")  # 0,005 normalizzato
    assert (c9102["AUDBTP"]["ter_pct"], c9102["AUDBTP"]["ter_source"]) == (0.0, "inferred")
    c9103 = tools.call("get_cost_breakdown", {"portfolio_id": 9103})
    assert (c9103["weighted_ter_pct"], c9103["ter_coverage_pct"], c9103["missing_ter_symbols"]) == (0.227, 85.0, ["AUDTHM.DE"])
    assert "AUDTHM.DE" in c9103["coverage_note"]
    rows = {r["symbol"]: r for r in c9103["position_costs"]}
    assert rows["AUDGLD.DE"]["ter_source"] == "justetf" and rows["AUDGLD.DE"]["ter_pct"] == 0.25
    others = {p: tools.call("get_cost_breakdown", {"portfolio_id": p})["weighted_ter_pct"] for p in (9102, 9104, 9105, 9107)}
    assert others == {9102: 0.232, 9104: 0.162, 9105: 0.18, 9107: 0.17}


def test_income_projection_buckets(tools):
    i9101 = tools.call("get_income_projection", {"portfolio_id": 9101})
    assert (i9101["equity_annual_dividends_eur"], i9101["fixed_income_annual_dividends_eur"]) == (60.0, 0.0)
    i9102 = tools.call("get_income_projection", {"portfolio_id": 9102})
    assert (i9102["equity_annual_dividends_eur"], i9102["fixed_income_annual_dividends_eur"]) == (0.0, 1324.1)
    assert i9102["current_annual_dividends_gross_eur"] == 1324.1
    i9104 = tools.call("get_income_projection", {"portfolio_id": 9104})
    assert i9104["fixed_income_annual_dividends_eur"] == 280.8


def test_dividend_summary_by_currency(tools):
    d9104 = tools.call("get_dividend_summary", {"portfolio_id": 9104})
    assert d9104["mixed_currencies"] is True and d9104["total_dividends_received"] is None
    assert d9104["dividends_by_currency"] == {"EUR": {"total": 15.0, "last_12m": 15.0, "count": 1},
                                              "GBP": {"total": 82.0, "last_12m": 82.0, "count": 2}}
    d9105 = tools.call("get_dividend_summary", {"portfolio_id": 9105})
    assert (d9105["dividends_currency"], d9105["total_dividends_received"], d9105["dividend_transactions_count"]) == ("EUR", 48.0, 4)
    d9101 = tools.call("get_dividend_summary", {"portfolio_id": 9101})
    assert (d9101["dividends_currency"], d9101["total_dividends_received"], d9101["dividend_transactions_count"]) == ("EUR", 62.5, 2)


def test_monte_carlo_has_history(tools):
    results = [tools.call("get_monte_carlo", {"portfolio_id": p}) for p in (9101, 9103)]
    results.append(tools.call("get_aggregate_monte_carlo", {"portfolio_ids": PORTFOLIO_IDS}))
    for mc in results:
        assert [p["year"] for p in mc["projections"]] == list(range(1, 11))
        assert mc["unit"] == "indice_base_100" and mc["initial_value"] == 100
        assert all(0 < p["p25"] <= p["p50"] <= p["p75"] for p in mc["projections"])


def test_day_movers(tools):
    dm = tools.call("get_day_movers", {"portfolio_id": 9107})
    assert (dm["valid_positions"], dm["excluded_stale"], dm["excluded_no_previous_close"]) == (1, 1, 1)
    assert dm["best"]["symbol"] == dm["worst"]["symbol"] == "AUDEQ.MI"
    assert [s["symbol"] for s in dm["stale_positions"]] == ["AUDSTL.MI"]
    rows = {r["symbol"]: r for r in _positions(tools, 9107)}
    assert rows["AUDSTL.MI"]["price_stale"] is True and rows["AUDNPC.MI"]["day_change_pct"] == 0
    dm9101 = tools.call("get_day_movers", {"portfolio_id": 9101})
    assert dm9101["valid_positions"] == 3
    assert all(r["day_change_pct"] != 0 and not r["price_stale"] for r in _positions(tools, 9101))
    summary = tools.call("get_portfolio_summary", {"portfolio_id": 9107})
    assert summary["stale_price_symbols"] == ["AUDSTL.MI"] and summary.get("data_quality_note")


# ---------------------------------------------------------------------------
# Gruppo D — coerenza fra tool, vista aggregata, dati
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9104, 9105])
def test_performance_export_matches_summary(tools, pid):
    export = tools.performance_audit(pid)
    summary = tools.call("get_portfolio_summary", {"portfolio_id": pid})
    current = export["service_results"]["current_value"]
    assert abs(summary["market_value"] + summary["cash_balance"] - current) <= 0.005 * 5 + 1e-6 * current
    check = export["consistency_check"]
    assert check["flows_match_service"] and check["count_match"] and check["totals_match"]


def test_twr_window_has_deposit_and_buys_9101(tools):
    """C1-TWR-MIXED: deposito e acquisti nella stessa finestra di un anno."""
    tx = tools.repo.list_transactions(9101, USER)
    cutoff = date.today() - timedelta(days=365)

    def day(t):
        value = t.get("trade_at") if isinstance(t, dict) else getattr(t, "trade_at")
        return value.date()

    sides = {(t.get("side") if isinstance(t, dict) else t.side) for t in tx if day(t) > cutoff}
    assert {"deposit", "buy", "sell", "dividend"} <= sides
    perf = tools.call("get_performance", {"portfolio_id": 9101})
    export = tools.performance_audit(9101)
    assert abs(perf["twr_1y"] - round(export["service_results"]["twr"]["twr_pct"], 2)) <= 0.005
    assert (perf["twr_1y"], perf["mwr_1y"]) == (9.26, 9.26)
    assert tools.call("get_performance", {"portfolio_id": 9104})["twr_1y"] == 3.95
    assert tools.call("get_performance", {"portfolio_id": 9105})["twr_1y"] == 2.73


def test_no_duplicate_transactions_and_one_legit_pair(seed_db):
    """D-DUP-TRANSACTIONS: nessun duplicato reale; 9105 ha una sola coppia legittima di acquisti."""
    rows = _rows(seed_db["engine"], """
        select portfolio_id, asset_id, side, (trade_at at time zone 'UTC')::date as d, trade_currency,
               quantity::float8 as q, price::float8 as p, fees::float8 as f, count(*) as n
        from transactions where owner_user_id = :u
        group by 1, 2, 3, 4, 5, 6, 7, 8 having count(*) > 1""", u=USER)
    assert [(r["portfolio_id"], r["side"], r["n"]) for r in rows] == [(9105, "buy", 2)]
    assert not [r for r in rows if r["side"] in CASH_SIDES]


@pytest.mark.parametrize("pid", [9101, 9104])
def test_trade_prices_on_market_scale(tools, pid):
    """D-TRADE-PRICE-SCALE: prezzi delle operazioni entro 1/20…20 del prezzo di mercato."""
    market = {r["symbol"]: r["market_price"] for r in _positions(tools, pid) if r["price_fallback"] is None}
    rows = _rows(tools.engine, """
        select a.symbol, t.price::float8 as price from transactions t join assets a on a.id = t.asset_id
        where t.portfolio_id = :p and t.side in ('buy', 'sell')""", p=pid)
    comparable = [r for r in rows if r["symbol"] in market]
    assert comparable
    assert all(1 / 20 <= r["price"] / market[r["symbol"]] <= 20 for r in comparable)


def test_summary_weights_cash_and_xray(tools):
    for pid in NON_EMPTY:
        rows = _positions(tools, pid)
        assert len(rows) < 30
        assert abs(sum(r["weight"] for r in rows) - 100) <= max(0.05, 0.005 * len(rows))
        summary = tools.call("get_portfolio_summary", {"portfolio_id": pid})
        assert abs(summary["market_value"] - sum(r["market_value"] for r in rows)) <= 0.005 * len(rows) + 0.01
        cash = tools.call("get_cash_balance", {"portfolio_id": pid})
        signs = {"opening_balance": 1, "deposits": 1, "dividends": 1, "interest": 1, "sells": 1,
                 "implicit_contributions": 1, "withdrawals": -1, "fees": -1, "buys": -1}
        assert set(cash["cash_breakdown"]) == set(signs)
        assert abs(sum(signs[k] * v for k, v in cash["cash_breakdown"].items()) - cash["total_cash"]) <= 0.06
    for pid in (9101, 9103):
        xray = tools.call("get_xray_summary", {"portfolio_id": pid})
        geo = xray["geographic_exposure"]
        assert geo and abs(sum(geo.values()) - 100) <= max(0.05, 0.005 * len(geo))


def test_doctor_metrics_available(tools):
    for pid in (9101, 9103):
        metrics = {m["code"]: m for m in tools.call("read_doctor_metrics", {"portfolio_id": pid})["metrics"]}
        cost = tools.call("get_cost_breakdown", {"portfolio_id": pid})["weighted_ter_pct"]
        health = tools.call("get_portfolio_health", {"portfolio_id": pid})
        assert abs(metrics["weighted_ter_pct"]["value"] - cost) <= 0.01
        assert abs(health["weighted_ter"] - cost) <= 0.01
        assert abs(metrics["max_single_position_pct"]["value"] - health["max_position_weight"]) <= 0.02
    gold = {m["code"]: m for m in tools.call("read_doctor_metrics", {"portfolio_id": 9103})["metrics"]}["gold_weight_pct"]
    assert gold["lower"] == 40.0


def test_empty_portfolio_9106(tools):
    assert _positions(tools, 9106) == []
    assert tools.call("get_stress_test", {"portfolio_id": 9106})["scenarios"] == []
    assert tools.call("get_cash_balance", {"portfolio_id": 9106})["total_cash"] == 0.0
    # TASK-87: X-Ray vuoto dichiarato, non l'errore generico del tool.
    xray = tools.call("get_xray_summary", {"portfolio_id": 9106})
    assert xray["is_empty"] is True and xray["coverage_pct"] == 0.0
    assert xray["top_underlying_holdings"] == [] and xray["funds"] == []
    assert xray["geographic_exposure"] == {} and xray["sector_exposure"] == {}
    assert xray["coverage_note"] == "Portafoglio senza posizioni: niente da scomporre."


def test_doctor_cash_is_current_cash_task84(tools):
    """TASK-84 (S-2026-11-11-01): il Doctor e lo Scenario Lab vedono la liquidità del riepilogo."""
    scenario = tools.call("build_doctor_scenario", {
        "portfolio_id": 9101, "mode": "manual", "constraints": {"use_cash_balance": True},
        "operations": [{"symbol": "AUDBD.MI", "action": "buy", "amount": 5000}],
    })
    assert scenario["feasible"] is True, scenario.get("infeasible_reason")
    assert scenario["infeasible_code"] is None and not scenario["required_new_cash"]
    assert scenario["before"]["cash_value"] == 9256.50
    assert scenario["before"]["total_value"] == 109256.50
    assert scenario["after"]["cash_value"] == 4256.50
    for pid in PORTFOLIO_IDS:
        before = tools.call("build_doctor_scenario", {"portfolio_id": pid, "mode": "new_cash_only", "new_cash": 100.0})["before"]
        summary = tools.call("get_portfolio_summary", {"portfolio_id": pid})
        assert before["cash_value"] == DOCUMENTED[pid][1] == summary["cash_balance"]
        assert before["total_value"] == round(summary["market_value"] + summary["cash_balance"], 2)
    before = tools.call("build_doctor_scenario", {"portfolio_id": 9101, "portfolio_ids": PORTFOLIO_IDS,
                                                  "mode": "new_cash_only", "new_cash": 100.0})["before"]
    assert before["cash_value"] == 33190.47
    assert before["cash_value"] == tools.call("get_aggregate_summary", {"portfolio_ids": PORTFOLIO_IDS})["cash_balance"]


# ---------------------------------------------------------------------------
# AC #2: ogni regola del catalogo ha un portafoglio di prova su cui non va in skip
# ---------------------------------------------------------------------------


def _has_positions(tools, pid):
    return bool(_positions(tools, pid))


def _hist_available(tools, pid):
    return any(s["scenario_type"] == "historical" and s["method"] != "not_available" for s in _stress(tools, pid).values())


def _has_targets(tools, pid):
    return all("totals" in tools.call("calculate_rebalance_orders", {"portfolio_id": pid, **a}) for a in ALL_ARGS_REBALANCE)


def _has_dividend_tx(tools, pid):
    return any((t.get("side") if isinstance(t, dict) else t.side) == "dividend" for t in tools.repo.list_transactions(pid, USER))


def _has_transactions(tools, pid):
    return bool(tools.repo.list_transactions(pid, USER))


def _info_of(tools, scope):
    return _info(tools, scope[0], scope[1])


AGG = "aggregate"


def _precondition(tools, rule_id: str, scope) -> bool:  # noqa: C901 - tabella delle precondizioni
    pid = scope if isinstance(scope, int) else None
    if scope == AGG:
        return bool(tools.call("get_aggregate_positions", {"portfolio_ids": PORTFOLIO_IDS})["positions"])
    if scope == "user":
        return sum(1 for p in PORTFOLIO_IDS if _hist_available(tools, p)) >= 2
    if isinstance(scope, tuple):  # instrument
        info = _info_of(tools, scope)
        if rule_id == "A-CLASS-ETC-NOT-EQUITY":
            return info["instrument_type"] in ("etc", "etn")
        if rule_id == "A-CLASS-ETP-TER-NONZERO":
            costs = tools.call("get_cost_breakdown", {"portfolio_id": scope[0]})["position_costs"]
            return info["instrument_type"] in ("etc", "etn", "etf", "fund") and any(r["symbol"] == scope[1] for r in costs)
        if rule_id == "A-CLASS-BOND-TYPE":
            return info["type"] == "bond"
        if rule_id == "A-CLASS-UNKNOWN-DECLARED":
            return info["asset_class"] == "unknown"
        if rule_id == "D-LSE-QUOTE-CURRENCY":
            return scope[1].upper().endswith(".L")
        return True  # D-HELD-SYMBOL-MATCH: nessuno skip
    if rule_id == "D-CASH-CONSISTENCY":
        return True
    if rule_id == "D-DOCTOR-CASH":  # TASK-84: anche il portafoglio vuoto (0 = 0); skip solo con 30 righe
        return len(_positions(tools, pid)) < 30
    if rule_id == "D-XRAY-EMPTY":  # TASK-87: valutata solo sul portafoglio vuoto
        return not _has_positions(tools, pid)
    if not _has_positions(tools, pid):
        return False
    if rule_id.startswith("A-STRESS") or rule_id == "A-CLASS-STRESS-CONSISTENT":
        if rule_id == "A-STRESS-NONEQUITY-POSITION-SHOCK":
            return any(s.get("most_impacted") for s in _stress(tools, pid).values())
        return _hist_available(tools, pid) or rule_id in ("A-STRESS-CONTRIB-SUM", "A-STRESS-SHOCK-TABLE")
    if rule_id.startswith("B-REB") or rule_id.startswith("B-PAC") or rule_id == "B-DRIFT-REBALANCE-WEIGHTS":
        if not _has_targets(tools, pid):
            return False
        if rule_id in ("B-REB-SELLS-REACH-TARGET", "B-REB-DRIFT-NONINCREASING"):
            return any(tools.call("calculate_rebalance_orders", {"portfolio_id": pid, **a})["orders"] for a in ALL_ARGS_REBALANCE)
        if rule_id == "B-REB-SELL-CAP":
            return any(o["side"] == "sell" for a in ALL_ARGS_REBALANCE
                       for o in tools.call("calculate_rebalance_orders", {"portfolio_id": pid, **a})["orders"])
        if rule_id.startswith("B-PAC"):
            return bool(tools.call("calculate_pac_contribution", {"portfolio_id": pid, "monthly_amount": 500.0})["distribution"])
        return True
    if rule_id == "B-WHATIF-SELL-BOUND":
        return _positions(tools, pid)[0]["market_value"] >= 0.02
    if rule_id == "C-TER-RANGE":
        return any(r["ter_pct"] is not None for r in tools.call("get_cost_breakdown", {"portfolio_id": pid})["position_costs"])
    if rule_id == "C-INCOME-CLASS-RECOMPUTE":
        return any((_info(tools, pid, r["symbol"]).get("dividend_yield") or 0) > 0 for r in _positions(tools, pid))
    if rule_id.startswith("C-MC"):
        return bool(tools.call("get_monte_carlo", {"portfolio_id": pid})["projections"])
    if rule_id == "C-DIV-CURRENCY":
        return _has_dividend_tx(tools, pid)
    if rule_id == "C-DAYMOVERS-NONZERO-INCLUDED":
        return any(not r["price_stale"] and r["price_date"] and r["day_change_pct"] != 0 for r in _positions(tools, pid))
    if rule_id == "C-DAYCHANGE-DENOMINATOR":  # TASK-86: tutte le posizioni nella valuta base, una variazione
        base = tools.call("get_portfolio_summary", {"portfolio_id": pid})["base_currency"]
        rows = _positions(tools, pid)
        return (all(_info(tools, pid, r["symbol"])["currency"] == base for r in rows)
                and any(r["day_change_pct"] != 0 for r in rows))
    if rule_id in ("D-SUMMARY-PERFORMANCE-VALUE", "D-PERF-RECOMPUTE", "D-PERF-TOOL-MATCH", "D-DUP-TRANSACTIONS"):
        return _has_transactions(tools, pid)
    if rule_id == "D-TRADE-PRICE-SCALE":
        held = {r["symbol"] for r in _positions(tools, pid) if r["price_fallback"] is None and r["market_price"] > 0}
        return _has_transactions(tools, pid) and bool(held)
    if rule_id == "D-DOCTOR-TER":
        metrics = {m["code"]: m for m in tools.call("read_doctor_metrics", {"portfolio_id": pid})["metrics"]}
        health = tools.call("get_portfolio_health", {"portfolio_id": pid})
        cost = tools.call("get_cost_breakdown", {"portfolio_id": pid})
        no_cash = all(_info(tools, pid, r["symbol"])["type"] != "cash" for r in _positions(tools, pid))
        return None not in (metrics["weighted_ter_pct"]["value"], health["weighted_ter"], cost["weighted_ter_pct"]) and no_cash
    if rule_id == "D-DOCTOR-CONCENTRATION":
        metrics = {m["code"]: m for m in tools.call("read_doctor_metrics", {"portfolio_id": pid})["metrics"]}
        return metrics["max_single_position_pct"]["value"] is not None
    return True  # regole che saltano solo con portafoglio vuoto o output troncato (< 30 righe qui)


def _instrument_scopes(symbol_filter=None):
    scopes = []
    for pid in NON_EMPTY:
        for symbol in DOCUMENTED[pid][2]:
            if symbol_filter is None or symbol_filter(symbol):
                scopes.append((pid, symbol))
    return scopes


# Colonna «Prova» del catalogo (rules.md §2-§5): regola -> scope su cui deve essere valutata.
PROOF = {
    "A-STRESS-HIST-DISTINCT": ["user"],
    "A-STRESS-PROXY-TABLE": [9102, 9103, AGG],
    "A-STRESS-METHOD-COVERAGE": [9101, 9102, AGG],
    "A-STRESS-CONTRIB-SUM": [9101, 9102, 9103, AGG],
    "A-STRESS-SHOCK-TABLE": [9102, 9103, 9101],
    "A-STRESS-NONEQUITY-POSITION-SHOCK": [9101, 9103],
    "A-CLASS-STRESS-CONSISTENT": [9101, 9102, 9103],
    "A-CLASS-ETC-NOT-EQUITY": [(9103, "AUDGLD.DE")],
    "A-CLASS-ETP-TER-NONZERO": [(9101, "AUDEQ.MI"), (9101, "AUDBD.MI"), (9101, "AUDTECH.DE"),
                                (9103, "AUDGLD.DE"), (9103, "AUDCMD.MI"), (9103, "AUDTHM.DE"), (9103, "AUDEQ.MI")],
    "A-CLASS-BOND-TYPE": [(9102, "AUDBTP")],
    "A-CLASS-UNKNOWN-DECLARED": [(9103, "AUDTHM.DE")],
    "B-REB-CASH-CONSERVATION": [9101],
    "B-REB-CASH-NONNEG": [9101],
    "B-REB-SELLS-REACH-TARGET": [9101],
    "B-REB-DRIFT-NONINCREASING": [9101],
    "B-REB-MODE-SIDES": [9101],
    "B-REB-SELL-CAP": [9101],
    "B-PAC-SUM": [9101],
    "B-PAC-UNDERWEIGHT-ONLY": [9101],
    "B-DRIFT-REBALANCE-WEIGHTS": [9101],  # TASK-85: skip solo senza target (drift vuoto)
    "B-WHATIF-BUY-WEIGHT": [9101],
    "B-WHATIF-SELL-BOUND": [9101],
    "C-TER-RANGE": [9101, 9102, 9103],
    "C-COST-COHERENCE": [9101, 9103],
    "C-COST-COVERAGE-DECLARED": [9103, 9101],
    "C-INCOME-BUCKETS-SUM": [9101, 9102],
    "C-INCOME-CLASS-RECOMPUTE": [9102, 9101],
    "C-MC-YEARS": [9101, 9103, AGG],
    "C-MC-PERCENTILES": [9101, 9103, AGG],
    "C-MC-MEDIAN-DRIFT": [9101, AGG],
    "C-DIV-CURRENCY": [9104, 9105, 9101],
    "C-DAYMOVERS-NONZERO-INCLUDED": [9101, 9107],
    "C-DAYMOVERS-CONSISTENCY": [9107, 9101],
    "C-DAYCHANGE-DENOMINATOR": [9107, 9101],
    "D-WEIGHTS-SUM": [*NON_EMPTY, AGG],
    "D-SUMMARY-POSITIONS": [*NON_EMPTY, AGG],
    "D-POSITION-VALUE-PRICE": [*NON_EMPTY, AGG],
    "D-CASH-CONSISTENCY": PORTFOLIO_IDS,
    "D-SUMMARY-PERFORMANCE-VALUE": [9101, 9104, AGG],
    "D-AGG-SUMS": [AGG],
    "D-AGG-POSITIONS": [AGG],
    "D-AGG-PERFORMANCE-VALUE": [AGG],
    "D-PERF-RECOMPUTE": [9101, 9104, AGG],
    "D-PERF-TOOL-MATCH": [9101, AGG],
    "D-DOCTOR-TER": [9101, 9103],
    "D-DOCTOR-CLASS-WEIGHTS": [9101, 9102, 9103],
    "D-DOCTOR-CONCENTRATION": [9101, 9103],
    "D-DOCTOR-CASH": [*PORTFOLIO_IDS, AGG],
    "D-HEALTH-SCORE-BREAKDOWN": [9101, 9103, AGG],
    "D-XRAY-SUMS": [9101, 9103, AGG],
    "D-XRAY-EMPTY": [9106],
    "D-DUP-TRANSACTIONS": [9105, 9101, 9104],
    "D-TRADE-PRICE-SCALE": [9101, 9104],
    "D-LSE-QUOTE-CURRENCY": [(9104, "AUDUS.L"), (9104, "AUDUK.L")],
    "D-FX-FLAGS-DECLARED": [9107, 9101, 9102, 9103, 9104, 9105],
    "D-HELD-SYMBOL-MATCH": _instrument_scopes(),
}


def test_proof_table_covers_the_whole_catalog():
    catalog = (REPO_ROOT / "docs" / "auditor" / "rules.md").read_text(encoding="utf-8")
    import re

    rule_ids = re.findall(r"^### ([ABCD]-[A-Z0-9-]+)\s*$", catalog, flags=re.MULTILINE)
    # Totale dichiarato in testa al catalogo (rules.md: «Totale: **N regole**»).
    assert len(rule_ids) == int(re.search(r"^Totale: \*\*(\d+) regole\*\*", catalog, re.MULTILINE).group(1))
    assert sorted(PROOF) == sorted(rule_ids)


@pytest.mark.parametrize("rule_id", sorted(PROOF))
def test_every_rule_has_a_non_skipping_proof_portfolio(tools, rule_id):
    failing = [scope for scope in PROOF[rule_id] if not _precondition(tools, rule_id, scope)]
    assert not failing, f"{rule_id}: precondizione non soddisfatta su {failing}"


def test_scopes_derived_from_the_seed(tools):
    """rules.md §1: 7 scope portfolio, 1 aggregato (7 portafogli EUR), uno scope instrument per posizione."""
    portfolios = tools.call("list_portfolios", {})["portfolios"]
    assert len(portfolios) == 7 and len({p["base_currency"] for p in portfolios}) == 1
    assert sum(len(_positions(tools, p)) for p in PORTFOLIO_IDS) == 18
    assert math.isclose(sum(len(DOCUMENTED[p][2]) for p in PORTFOLIO_IDS), 18)
