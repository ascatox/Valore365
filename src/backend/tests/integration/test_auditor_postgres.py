"""TASK-79: l'Auditor dei calcoli sul seed dei portafogli di prova, su un PostgreSQL 16 reale.

Applica ``database/schema.sql``, tutte le migrazioni e ``scripts/auditor/audit_seed.sql`` in un
database dedicato del cluster della fixture ``pg_engine``, esegue l'Auditor (le 52 regole, tutti gli
scope dell'utente ``auditor-seed-user``) e verifica, sul codice attuale:

- nessun ``fail`` né ``error`` fuori dai difetti noti (regole con ``known_defect``), a ogni severità;
- nessuna regola in ``skip`` su uno scope della colonna «Prova» del catalogo (``docs/auditor/rules.md``);
- i ``known_defect`` delle dichiarazioni coincidono con la sezione «Difetti noti» del catalogo;
- la CLI della CI (``--mode ci --fail-on P1 --strict-known``) esce con 0 e scrive JSON valido e Markdown;
- B-PAC-SUM con nessuno strumento sottopesato (target 45/20 su 9105, ex difetto noto TASK-83)
  dà ``pass`` e l'uscita è 0 anche con ``--strict-known``; con gli stessi target (somma 65, importo
  oltre il fabbisogno) anche B-PAC-UNDERWEIGHT-ONLY e B-PAC-NO-OVERSHOOT danno ``pass`` (TASK-90);
- B-PAC-NO-OVERSHOOT su 9101 (TASK-90): ``pass`` sul codice attuale, ``fail`` con la ripartizione
  di prima reintrodotta.

I tool del Doctor usano il servizio di processo legato al ``DATABASE_URL`` dell'app: qui viene
sostituito con uno legato al database del seed (architecture.md, Deviazioni TASK-78). La rete è
bloccata per tutta l'esecuzione in processo. Saltato quando i binari di Postgres mancano.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.mcp_server.tools import ToolDependencies
from app.repository import PortfolioRepository
from app.services.auditor.context import AuditContext, OfflineFinanceClient
from app.services.auditor.registry import load_rules
from app.services.auditor.report import report_to_markdown, validate_report
from app.services.auditor.runner import RunOptions, exit_code_for, run_audit
from app.services.performance_service import PerformanceService

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]
DATABASE_DIR = REPO_ROOT / "database"
SEED = REPO_ROOT / "scripts" / "auditor" / "audit_seed.sql"
RULES_MD = REPO_ROOT / "docs" / "auditor" / "rules.md"
DB_NAME = "auditor_ci"
USER = "auditor-seed-user"
PORTFOLIO_IDS = [9101, 9102, 9103, 9104, 9105, 9106, 9107]
NON_EMPTY = [9101, 9102, 9103, 9104, 9105, 9107]
AGG = "aggregate:" + ",".join(str(p) for p in PORTFOLIO_IDS)
USER_SCOPE = "user"

# Simboli detenuti per portafoglio (scripts/auditor/README.md).
HOLDINGS = {
    9101: ["AUDEQ.MI", "AUDBD.MI", "AUDTECH.DE"],
    9102: ["AUDGOV.MI", "AUDHY.DE", "AUDBTP"],
    9103: ["AUDGLD.DE", "AUDEQ.MI", "AUDCMD.MI", "AUDTHM.DE"],
    9104: ["AUDUS.L", "AUDUK.L", "AUDEQ.MI"],
    9105: ["AUDEQ.MI", "AUDBD.MI"],
    9106: [],
    9107: ["AUDSTL.MI", "AUDEQ.MI", "AUDNPC.MI"],
}


def _p(pid: int) -> str:
    return f"portfolio:{pid}"


def _i(pid: int, symbol: str) -> str:
    return f"instrument:{pid}:{symbol}"


# Colonna «Prova» di docs/auditor/rules.md, come scope_key: su questi scope la regola deve essere
# valutata (pass o fail), mai skip. Stessa lettura della tabella PROOF di
# test_auditor_seed_postgres.py (TASK-78), che ne verifica le precondizioni sui tool.
PROOF: dict[str, list[str]] = {
    "A-STRESS-HIST-DISTINCT": [USER_SCOPE],
    "A-STRESS-PROXY-TABLE": [_p(9102), _p(9103), AGG],
    "A-STRESS-METHOD-COVERAGE": [_p(9101), _p(9102), AGG],
    "A-STRESS-CONTRIB-SUM": [_p(9101), _p(9102), _p(9103), AGG],
    "A-STRESS-SHOCK-TABLE": [_p(9102), _p(9103), _p(9101)],
    "A-STRESS-NONEQUITY-POSITION-SHOCK": [_p(9101), _p(9103)],
    "A-CLASS-STRESS-CONSISTENT": [_p(9101), _p(9102), _p(9103)],
    "A-CLASS-ETC-NOT-EQUITY": [_i(9103, "AUDGLD.DE")],
    "A-CLASS-ETP-TER-NONZERO": [_i(9101, "AUDEQ.MI"), _i(9101, "AUDBD.MI"), _i(9101, "AUDTECH.DE"),
                                _i(9103, "AUDGLD.DE"), _i(9103, "AUDCMD.MI"), _i(9103, "AUDTHM.DE"),
                                _i(9103, "AUDEQ.MI")],
    "A-CLASS-BOND-TYPE": [_i(9102, "AUDBTP")],
    "A-CLASS-UNKNOWN-DECLARED": [_i(9103, "AUDTHM.DE")],
    "B-REB-CASH-CONSERVATION": [_p(9101)],
    "B-REB-CASH-NONNEG": [_p(9101)],
    "B-REB-SELLS-REACH-TARGET": [_p(9101)],
    "B-REB-DRIFT-NONINCREASING": [_p(9101)],
    "B-REB-MODE-SIDES": [_p(9101)],
    "B-REB-SELL-CAP": [_p(9101)],
    "B-PAC-SUM": [_p(9101)],
    "B-PAC-UNDERWEIGHT-ONLY": [_p(9101)],
    "B-PAC-NO-OVERSHOOT": [_p(9101)],
    "B-DRIFT-REBALANCE-WEIGHTS": [_p(9101)],
    "B-WHATIF-BUY-WEIGHT": [_p(9101)],
    "B-WHATIF-SELL-BOUND": [_p(9101)],
    "C-TER-RANGE": [_p(9101), _p(9102), _p(9103)],
    "C-COST-COHERENCE": [_p(9101), _p(9103)],
    "C-COST-COVERAGE-DECLARED": [_p(9103), _p(9101)],
    "C-INCOME-BUCKETS-SUM": [_p(9101), _p(9102)],
    "C-INCOME-CLASS-RECOMPUTE": [_p(9102), _p(9101)],
    "C-MC-YEARS": [_p(9101), _p(9103), AGG],
    "C-MC-PERCENTILES": [_p(9101), _p(9103), AGG],
    "C-MC-MEDIAN-DRIFT": [_p(9101), AGG],
    "C-DIV-CURRENCY": [_p(9104), _p(9105), _p(9101)],
    "C-DIV-PROJECTION-MATCH": [_p(9102), _p(9104), _p(9101)],
    "C-DAYMOVERS-NONZERO-INCLUDED": [_p(9101), _p(9107)],
    "C-DAYMOVERS-CONSISTENCY": [_p(9107), _p(9101)],
    "C-DAYCHANGE-DENOMINATOR": [_p(9107), _p(9101)],
    "D-WEIGHTS-SUM": [*(_p(p) for p in NON_EMPTY), AGG],
    "D-SUMMARY-POSITIONS": [*(_p(p) for p in NON_EMPTY), AGG],
    "D-POSITION-VALUE-PRICE": [*(_p(p) for p in NON_EMPTY), AGG],
    "D-CASH-CONSISTENCY": [_p(p) for p in PORTFOLIO_IDS],
    "D-SUMMARY-PERFORMANCE-VALUE": [_p(9101), _p(9104), AGG],
    "D-AGG-SUMS": [AGG],
    "D-AGG-POSITIONS": [AGG],
    "D-AGG-PERFORMANCE-VALUE": [AGG],
    "D-PERF-RECOMPUTE": [_p(9101), _p(9104), AGG],
    "D-PERF-TOOL-MATCH": [_p(9101), AGG],
    "D-PERF-EMPTY-NULL": [_p(9106)],
    "D-DOCTOR-TER": [_p(9101), _p(9103)],
    "D-DOCTOR-CLASS-WEIGHTS": [_p(9101), _p(9102), _p(9103)],
    "D-DOCTOR-CONCENTRATION": [_p(9101), _p(9103)],
    "D-DOCTOR-CASH": [*(_p(p) for p in PORTFOLIO_IDS), AGG],
    "D-HEALTH-SCORE-BREAKDOWN": [_p(9101), _p(9103), AGG],
    "D-XRAY-SUMS": [_p(9101), _p(9103), AGG],
    "D-XRAY-EMPTY": [_p(9106)],
    "D-DUP-TRANSACTIONS": [_p(9105), _p(9101), _p(9104)],
    "D-TRADE-PRICE-SCALE": [_p(9101), _p(9104)],
    "D-LSE-QUOTE-CURRENCY": [_i(9104, "AUDUS.L"), _i(9104, "AUDUK.L")],
    "D-FX-FLAGS-DECLARED": [_p(9107), _p(9101), _p(9102), _p(9103), _p(9104), _p(9105)],
    "D-HELD-SYMBOL-MATCH": [_i(pid, s) for pid in NON_EMPTY for s in HOLDINGS[pid]],
    "D-TX-CASH-RECONCILE": [_p(9107), _p(9101), _p(9102), _p(9103), _p(9105)],
}


# ---------------------------------------------------------------------------
# Database del seed e dipendenze
# ---------------------------------------------------------------------------


def _psql_base(pg_engine) -> list[str]:
    url = pg_engine.url
    return ["psql", "-q", "-h", url.query["host"], "-p", str(url.query.get("port") or url.port),
            "-U", "postgres", "-v", "ON_ERROR_STOP=1"]


def _run_psql(psql: list[str], *args: str) -> None:
    subprocess.run([*psql, *args], check=True, capture_output=True, text=True, cwd="/")


def _db_url(pg_engine) -> str:
    url = pg_engine.url
    return f"postgresql+psycopg://postgres@/{DB_NAME}?host={url.query['host']}&port={url.query.get('port') or url.port}"


@pytest.fixture(scope="module")
def seed_db(pg_engine):
    psql = _psql_base(pg_engine)
    _run_psql(psql, "-d", "postgres", "-c", f"drop database if exists {DB_NAME}")
    _run_psql(psql, "-d", "postgres", "-c", f"create database {DB_NAME}")
    _run_psql(psql, "-d", DB_NAME, "-f", str(DATABASE_DIR / "schema.sql"))
    for migration in sorted((DATABASE_DIR / "migrations").glob("*.sql")):
        _run_psql(psql, "-d", DB_NAME, "-f", str(migration))
    _run_psql(psql, "-d", DB_NAME, "-f", str(SEED))
    engine = create_engine(_db_url(pg_engine), pool_size=3, max_overflow=3)
    yield {"engine": engine, "url": _db_url(pg_engine)}
    engine.dispose()
    subprocess.run([*psql, "-d", "postgres", "-c", f"drop database if exists {DB_NAME}"], capture_output=True, cwd="/")


@pytest.fixture(scope="module")
def audit_env(seed_db):
    """Dipendenze dell'Auditor sul DB del seed (come build_tool_dependencies), Doctor rilegato, rete bloccata."""
    import app.services.doctor_policy.service as doctor_service

    repo = PortfolioRepository(seed_db["engine"])
    deps = ToolDependencies(repo=repo, performance_service=PerformanceService(repo), finance_client=OfflineFinanceClient())
    patcher = pytest.MonkeyPatch()
    patcher.setattr(doctor_service, "_default_service", doctor_service.DoctorPolicyService(repo))
    real_connect = socket.socket.connect

    def _no_network(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError(f"rete non ammessa durante l'audit: {address!r}")
        return real_connect(sock, address)

    patcher.setattr(socket.socket, "connect", _no_network)

    def run(options: RunOptions) -> dict:
        ctx = AuditContext(deps, USER, run_id=uuid.uuid4().hex, mode=options.mode)
        report = run_audit(ctx, load_rules(), options)
        validate_report(report)
        return report

    yield run
    patcher.undo()


@pytest.fixture(scope="module")
def report(audit_env) -> dict:
    return audit_env(RunOptions(mode="ci", fail_on="P1"))


def _describe(results) -> str:
    lines = []
    for r in results:
        evidence = "; ".join(
            f"{e.get('path')} ({e.get('tool')}): {e.get('observed')!r} → {e.get('expected')!r}"
            for e in (r.get("evidence") or [])[:5]
        )
        lines.append(f"{r['status']} {r['severity']} {r['rule_id']} {r['scope_key']} [{r['reason_code']}] "
                     f"{r['reason']} — {evidence}")
    return "\n".join(lines)


def _known_defects_from_catalog() -> dict[str, str]:
    """Righe della tabella di rules.md §6: `RULE-ID` -> TASK-NN."""
    text_md = RULES_MD.read_text(encoding="utf-8")
    section = text_md.split("## 6. Difetti noti", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `([ABCD]-[A-Z0-9-]+)` \|.*\| (TASK-\d+) \| [^|]+ \|\s*$", section, flags=re.MULTILINE)
    return dict(rows)


# ---------------------------------------------------------------------------
# Esecuzione completa sul seed
# ---------------------------------------------------------------------------


def test_full_run_covers_catalog_and_seed(report):
    catalog_ids = re.findall(r"^### ([ABCD]-[A-Z0-9-]+)\s*$", RULES_MD.read_text(encoding="utf-8"), flags=re.MULTILINE)
    # Totale dichiarato in testa al catalogo (rules.md: «Totale: **N regole**»).
    declared = int(re.search(r"^Totale: \*\*(\d+) regole\*\*", RULES_MD.read_text(encoding="utf-8"), re.MULTILINE).group(1))
    assert len(catalog_ids) == declared
    assert sorted(r["id"] for r in report["rules"]) == sorted(catalog_ids)
    assert sorted(PROOF) == sorted(catalog_ids)
    scope_keys = {s["scope_key"] for s in report["scopes"]}
    expected = {_p(p) for p in PORTFOLIO_IDS} | {AGG, USER_SCOPE}
    expected |= {_i(pid, s) for pid in NON_EMPTY for s in HOLDINGS[pid]}
    assert scope_keys == expected
    assert report["mode"] == "ci" and report["user_id"] == USER
    assert report["deadline_exceeded"] is False


def test_no_fail_or_error_outside_known_defects(report):
    bad = [r for r in report["results"]
           if r["status"] == "error" or (r["status"] == "fail" and not r.get("known_defect"))]
    assert not bad, "fail/error fuori dai difetti noti:\n" + _describe(bad)
    assert report["exit_code"] == 0
    assert exit_code_for(report, fail_on="P2") == 0
    # Nessun difetto noto aperto (TASK-83 risolto): l'uscita è 0 anche con --strict-known.
    assert report["counts"]["known_defect_failures"] == 0
    assert exit_code_for(report, fail_on="P2", strict_known=True) == 0


def test_no_skip_where_catalog_expects_evaluation(report):
    by_key = {(r["rule_id"], r["scope_key"]): r for r in report["results"]}
    missing = [(rule, key) for rule, keys in PROOF.items() for key in keys if (rule, key) not in by_key]
    assert not missing, f"nessun risultato per: {missing}"
    skipped = [by_key[(rule, key)] for rule, keys in PROOF.items() for key in keys
               if by_key[(rule, key)]["status"] == "skip"]
    assert not skipped, "skip dove il catalogo prevede la valutazione:\n" + _describe(skipped)


def test_every_rule_is_evaluated_at_least_once(report):
    never = [rule for rule, counts in report["by_rule"].items() if counts["pass"] + counts["fail"] == 0]
    assert not never, f"regole mai valutate sul seed: {never}"


def test_known_defects_match_catalog_section(report):
    declared = {r["id"]: r["known_defect"] for r in report["rules"] if r.get("known_defect")}
    assert declared == _known_defects_from_catalog()
    for task in declared.values():
        number = task.split("-")[1]
        assert list((REPO_ROOT / "backlog" / "tasks").glob(f"task-{number} - *.md")), f"{task} non è nel backlog"


def test_markdown_report_fits_job_summary(report):
    markdown = report_to_markdown(report)
    assert markdown.startswith("# Auditor dei calcoli — superato")
    assert len(markdown.encode("utf-8")) < 1024 * 1024


# ---------------------------------------------------------------------------
# CLI come in CI (.github/workflows/auditor.yml)
# ---------------------------------------------------------------------------


def test_cli_ci_mode_on_seed(seed_db, tmp_path):
    json_out, md_out = tmp_path / "auditor-report.json", tmp_path / "auditor-report.md"
    env = {**os.environ, "DATABASE_URL": seed_db["url"]}
    proc = subprocess.run(
        [sys.executable, "-m", "app.services.auditor", "--user", USER, "--mode", "ci", "--fail-on", "P1",
         "--strict-known", "--json-out", str(json_out), "--md-out", str(md_out)],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-4000:] + proc.stdout[-4000:]
    cli_report = json.loads(json_out.read_text(encoding="utf-8"))
    validate_report(cli_report)
    assert cli_report["exit_code"] == 0 and cli_report["mode"] == "ci"
    assert cli_report["counts"]["by_status"]["error"] == 0
    assert md_out.read_text(encoding="utf-8").startswith("# Auditor dei calcoli — superato")


# ---------------------------------------------------------------------------
# B-PAC-SUM senza strumenti sottopesati (ex difetto noto TASK-83, risolto)
# ---------------------------------------------------------------------------


def test_pac_sum_without_underweight_holding_passes_on_seed(seed_db, audit_env):
    """Target 45/20 su 9105 (pesi 48,67/24,34: nessuno strumento sottopesato).

    Da TASK-85 i pesi del PAC sono sul totale con la liquidità (10.000 + 5.000 + 5.545 =
    20.545 €), non più sulle sole posizioni (66,67/33,33): con i target 60/30 di prima
    entrambi gli strumenti risulterebbero sottopesati. Prima di TASK-83 `calculate_pac_contribution` rispondeva con distribuzione vuota e
    `total_allocated` 500 (difetto noto); da TASK-83 a TASK-90 non distribuiva nulla e lo
    dichiarava (`total_allocated` 0, `unallocated_amount` 500, nota). Da TASK-90 (decisione del
    proprietario) il fabbisogno sulla base dopo il versamento è 0 e i target sommano a 65: i 500 €
    vanno in proporzione ai target (346,15 / 153,85), con una nota. B-PAC-SUM,
    B-PAC-UNDERWEIGHT-ONLY e B-PAC-NO-OVERSHOOT danno `pass`, nessun difetto noto, e l'uscita è 0
    anche con `strict_known`.
    """
    engine = seed_db["engine"]
    with engine.begin() as conn:
        conn.execute(text(
            "insert into portfolio_target_allocations (portfolio_id, asset_id, weight_pct, owner_user_id) "
            "values (9105, 9101, 45, :u), (9105, 9102, 20, :u)"), {"u": USER})
    try:
        options = dict(mode="ci", portfolio_ids=[9105],
                       rule_ids=["B-PAC-SUM", "B-PAC-UNDERWEIGHT-ONLY", "B-PAC-NO-OVERSHOOT"],
                       include_aggregate=False, include_instruments=False)
        run = audit_env(RunOptions(**options))
        by_rule = {r["rule_id"]: r for r in run["results"]}
        assert set(by_rule) == set(options["rule_ids"])
        assert all(r["status"] == "pass" for r in by_rule.values()), _describe(run["results"])
        result = by_rule["B-PAC-SUM"]
        assert not result.get("known_defect")
        [evidence] = [e for e in result["evidence"] if e["path"] == "distribution[*].amount_eur"]
        assert evidence["observed"] == 500.0 and evidence["expected"] == 500.0
        assert run["counts"]["known_defect_failures"] == 0
        assert run["exit_code"] == 0
        strict = audit_env(RunOptions(**options, strict_known=True))
        assert all(r["status"] == "pass" for r in strict["results"]), _describe(strict["results"])
        assert strict["exit_code"] == 0
    finally:
        with engine.begin() as conn:
            conn.execute(text("delete from portfolio_target_allocations where portfolio_id = 9105"))


# ---------------------------------------------------------------------------
# B-PAC-NO-OVERSHOOT su 9101 (TASK-90)
# ---------------------------------------------------------------------------


def _legacy_pac(args, repo, _perf, portfolio_id, user_id, **_kw):
    """`_calculate_pac_contribution` prima di TASK-90: quote in proporzione allo scostamento attuale
    in punti, sulla base prima del versamento, solo fra gli strumenti oggi sottopesati, senza tetto."""
    from app.services.rebalance import TARGET_WEIGHT_BASIS_NOTE, current_target_weights

    amount_in = args.get("monthly_amount", 0)
    positions = repo.get_positions(portfolio_id, user_id) or []
    summary = repo.get_summary(portfolio_id, user_id)
    target_alloc = repo.list_portfolio_target_allocations(portfolio_id, user_id)
    if not target_alloc:
        return {"distribution": [], "note": "Nessun target configurato."}
    pos_map = {p.asset_id: p for p in positions}
    weights = current_target_weights(positions, target_alloc, float(summary.cash_balance or 0.0))
    rows = sorted(((ta, round(weights.current_weight_pct(ta.asset_id), 2)) for ta in target_alloc),
                  key=lambda r: r[1] - r[0].weight_pct)
    under = [(ta, cw) for ta, cw in rows if cw - ta.weight_pct < 0]
    total_cents = int(round(float(amount_in) * 100))
    neg = sum(ta.weight_pct - cw for ta, cw in under)
    raw = [(ta.weight_pct - cw) / neg * total_cents for ta, cw in under]
    cents = [int(c) for c in raw]
    for i in sorted(range(len(under)), key=lambda i: (cents[i] - raw[i], i))[: total_cents - sum(cents)]:
        cents[i] += 1
    new_total = weights.base_value + total_cents / 100
    dist = []
    for (ta, cw), c in zip(under, cents):
        pos = pos_map.get(ta.asset_id)
        value = (pos.market_value if pos else 0) + c / 100
        dist.append({"symbol": ta.symbol, "amount_eur": round(c / 100, 2), "shares_approx": None,
                     "current_weight": cw, "target_weight": round(ta.weight_pct, 2),
                     "new_weight_after": round(value / new_total * 100, 2)})
    return {"monthly_amount": amount_in, "distribution": dist, "total_allocated": round(sum(cents) / 100, 2),
            "unallocated_amount": 0.0, "total_value": round(weights.base_value, 2),
            "weight_basis_note": TARGET_WEIGHT_BASIS_NOTE}


def test_pac_no_overshoot_on_seed_9101(audit_env, monkeypatch):
    """S-2026-11-11-13: `pass` col codice attuale; con la ripartizione di prima reintrodotta
    `fail` (con A = 109.256,50 AUDBD.MI oltre il 40 %, AUDEQ.MI a 0), mentre B-PAC-SUM e
    B-PAC-UNDERWEIGHT-ONLY restano `pass`."""
    import app.copilot_tools as copilot_tools

    options = dict(mode="ci", portfolio_ids=[9101],
                   rule_ids=["B-PAC-SUM", "B-PAC-UNDERWEIGHT-ONLY", "B-PAC-NO-OVERSHOOT"],
                   include_aggregate=False, include_instruments=False)
    run = audit_env(RunOptions(**options))
    by_rule = {r["rule_id"]: r for r in run["results"]}
    assert all(r["status"] == "pass" for r in by_rule.values()), _describe(run["results"])
    ok = by_rule["B-PAC-NO-OVERSHOOT"]
    big = {e["path"]: e for e in ok["evidence"] if e["args"].get("monthly_amount") == 109256.5}
    assert big and all(e["observed"] <= e["expected"] + 0.02
                       for p, e in big.items() if p.endswith("new_weight_after"))

    monkeypatch.setitem(copilot_tools._TOOL_HANDLERS, "calculate_pac_contribution", _legacy_pac)
    legacy = {r["rule_id"]: r for r in audit_env(RunOptions(**options))["results"]}
    assert legacy["B-PAC-NO-OVERSHOOT"]["status"] == "fail", _describe(legacy.values())
    evidence = legacy["B-PAC-NO-OVERSHOOT"]["evidence"]
    assert any(e["args"].get("monthly_amount") == 109256.5 and e["path"].endswith("new_weight_after")
               and e["observed"] > 40.02 for e in evidence)
    assert any(e["path"] == "distribution[symbol=AUDEQ.MI].amount_eur" and e["observed"] == 0.0 for e in evidence)
    assert legacy["B-PAC-SUM"]["status"] == "pass" and legacy["B-PAC-UNDERWEIGHT-ONLY"]["status"] == "pass"
