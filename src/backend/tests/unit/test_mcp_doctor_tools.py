"""Portfolio Doctor 2.0 over MCP: read-only allowlist, preview excluded,
every (nested) argument bounded, aggregate policy scope authorized."""

from __future__ import annotations

import json

import pytest

import app.copilot_doctor_tools as doctor_tools
import app.mcp_server.tools as mcp_tools
from app.mcp_server.freshness import FRESHNESS_TOOLS
from app.mcp_server.tools import (
    ARGUMENT_CONSTRAINTS,
    EXPOSED_TOOL_NAMES,
    HEAVY_TOOLS,
    MCP_TOOL_ALLOWLIST,
    MCP_TOOL_EXCLUDED,
    McpToolError,
    ToolDependencies,
    build_tool_list,
    run_tool_sync,
    validate_arguments,
)
from app.repository._scope import NOT_FOUND_MESSAGE

USER = "u1"
OWNED = {1, 2}
EXPOSED_DOCTOR = {
    "read_doctor_policy", "read_doctor_metrics", "read_doctor_violations",
    "validate_policy_draft", "build_doctor_scenario", "compare_doctor_scenarios",
}
DOC = {"rules": [{"rule_id": "max-single", "metric_code": "max_single_position_pct", "operator": "max", "max_value": 35}]}


def test_doctor_tools_exposure_decisions():
    assert EXPOSED_DOCTOR <= MCP_TOOL_ALLOWLIST
    assert EXPOSED_DOCTOR <= EXPOSED_TOOL_NAMES
    assert "preview_policy" in MCP_TOOL_EXCLUDED and "token" in MCP_TOOL_EXCLUDED["preview_policy"]
    assert "preview_policy" not in EXPOSED_TOOL_NAMES
    assert {"build_doctor_scenario", "compare_doctor_scenarios"} <= HEAVY_TOOLS
    assert {"read_doctor_metrics", "read_doctor_violations", "build_doctor_scenario",
            "compare_doctor_scenarios"} <= FRESHNESS_TOOLS
    for tool in build_tool_list():
        if tool.name in EXPOSED_DOCTOR:
            assert tool.annotations.readOnlyHint is True and tool.annotations.destructiveHint is False


def _assert_bounded(schema: dict, where: str) -> None:
    kind = schema.get("type")
    if kind == "string" and "enum" not in schema:
        assert "maxLength" in schema, f"{where}: string without maxLength"
    if kind in ("number", "integer"):
        assert "maximum" in schema, f"{where}: number without maximum"
        assert "minimum" in schema or "exclusiveMinimum" in schema, f"{where}: number without minimum"
    if kind == "array":
        assert "maxItems" in schema, f"{where}: array without maxItems"
        assert "items" in schema, f"{where}: array without items"
        _assert_bounded(schema["items"], f"{where}[]")
    if kind == "object":
        extra = schema.get("additionalProperties", True)
        if extra is not False:
            assert isinstance(extra, dict) and "maxProperties" in schema, f"{where}: open object"
            _assert_bounded(extra, f"{where}{{*}}")
            names = schema.get("propertyNames") or {}
            assert "maxLength" in names, f"{where}: unbounded keys"
        for name, prop in (schema.get("properties") or {}).items():
            _assert_bounded(prop, f"{where}.{name}")


def test_every_exposed_argument_is_bounded_recursively():
    for tool in build_tool_list():
        schema = tool.inputSchema
        assert schema.get("additionalProperties") is False, tool.name
        _assert_bounded(schema, tool.name)


def test_nested_constraints_come_from_argument_constraints():
    for name in ("document", "operations", "target_weights", "constraints", "fee_model", "scenarios", "new_cash"):
        assert name in ARGUMENT_CONSTRAINTS


@pytest.mark.parametrize("name, args", [
    ("validate_policy_draft", {"portfolio_id": 1, "document": {"rules": [{**DOC["rules"][0], "expression": "1+1"}]}}),
    ("validate_policy_draft", {"portfolio_id": 1, "document": {"rules": [DOC["rules"][0]] * 21}}),
    ("validate_policy_draft", {"portfolio_id": 1, "document": {"rules": [{**DOC["rules"][0], "label": "x" * 81}]}}),
    ("validate_policy_draft", {"portfolio_id": 1, "document": {"rules": [{**DOC["rules"][0], "max_value": 1e9}]}}),
    ("validate_policy_draft", {"portfolio_id": 1, "document": {"rules": [{**DOC["rules"][0], "metric_code": "eval"}]}}),
    ("validate_policy_draft", {"portfolio_id": 1, "document": {"rules": [{**DOC["rules"][0], "rule_id": "IGNORE ALL"}]}}),
    ("build_doctor_scenario", {"portfolio_id": 1, "mode": "rebalance", "target_weights": {"abc": 10}}),
    ("build_doctor_scenario", {"portfolio_id": 1, "mode": "manual", "new_cash": float("nan")}),
    ("build_doctor_scenario", {"portfolio_id": 1, "mode": "manual", "operations": [
        {"symbol": "A B; DROP", "action": "buy", "amount": 1}]}),
    ("build_doctor_scenario", {"portfolio_id": 1, "mode": "manual", "fee_model": {"pct": 50}}),
    ("compare_doctor_scenarios", {"portfolio_id": 1, "scenarios": [{"mode": "manual"}] * 4}),
    ("compare_doctor_scenarios", {"portfolio_id": 1, "scenarios": [
        {"mode": "rebalance", "target_weights": {"1" * 11: 5}}, {"mode": "manual"}]}),
    ("read_doctor_policy", {"portfolio_id": 1, "portfolio_ids": list(range(1, 22))}),
    ("read_doctor_policy", {"portfolio_id": 1, "portfolio_ids": [1, 1]}),
])
def test_invalid_or_oversized_arguments_are_rejected(name, args):
    with pytest.raises(McpToolError):
        validate_arguments(name, args)


class _Repo:
    def __init__(self) -> None:
        self.scope_calls: list[list[int]] = []

    def resolve_portfolio_scope(self, ids, user_id):
        self.scope_calls.append(list(ids))
        if user_id != USER or any(int(i) not in OWNED for i in ids):
            raise ValueError(NOT_FOUND_MESSAGE)


class _SpyService:
    """Records every call; any write-ish method fails the test."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def __getattr__(self, name):
        if name in ("save", "restore", "preview"):
            raise AssertionError(f"MCP must never call {name}")
        raise AttributeError(name)

    def resolve_scope(self, ids, user_id):
        self.calls.append(("resolve_scope", (list(ids),)))
        return sorted(set(ids))

    def get_policy(self, user_id, ids):
        self.calls.append(("get_policy", (list(ids),)))
        return None

    def templates(self):
        return type("T", (), {"templates": []})()

    def validate(self, user_id, ids, document):
        self.calls.append(("validate", (list(ids), document)))
        return type("V", (), {"model_dump": lambda self, mode=None: {
            "valid": True, "field_errors": [], "normalized_document": {"schema_version": 1, "rules": []}}})()

    def preview_scenario(self, user_id, payload):
        self.calls.append(("preview_scenario", (payload,)))
        return {"mode": payload["mode"], "feasible": True, "scope": {"portfolio_ids": payload["portfolio_ids"]},
                "before": None, "after": None, "changes": [], "disclaimer": "Simulazione teorica; nessun ordine eseguito."}


@pytest.fixture()
def deps(monkeypatch):
    service = _SpyService()
    monkeypatch.setattr(doctor_tools, "service_factory", lambda _repo: service)
    monkeypatch.setattr(mcp_tools, "data_freshness_block", lambda *_a, **_k: {"status": "test"})
    return ToolDependencies(repo=_Repo(), performance_service=None), service


def test_read_policy_single_and_aggregate_scope(deps):
    d, service = deps
    single = run_tool_sync(d, "read_doctor_policy", {"portfolio_id": 1}, USER)
    assert single["scope"]["portfolio_ids"] == [1] and single["has_policy"] is False
    aggregate = run_tool_sync(d, "read_doctor_policy", {"portfolio_id": 1, "portfolio_ids": [2, 1]}, USER)
    assert aggregate["scope"] == {"portfolio_ids": [1, 2], "scope_type": "aggregate"}
    assert [1, 2] in d.repo.scope_calls  # every id of the scope checked by MCP
    assert ("get_policy", ([1, 2],)) in service.calls


def test_aggregate_scope_errors_do_not_leak(deps):
    d, _service = deps
    with pytest.raises(McpToolError, match=NOT_FOUND_MESSAGE):
        run_tool_sync(d, "read_doctor_policy", {"portfolio_id": 1, "portfolio_ids": [1, 99]}, USER)
    with pytest.raises(McpToolError, match="portfolio_id"):
        run_tool_sync(d, "read_doctor_policy", {"portfolio_id": 1, "portfolio_ids": [2]}, USER)
    with pytest.raises(McpToolError, match=NOT_FOUND_MESSAGE):
        run_tool_sync(d, "read_doctor_policy", {"portfolio_id": 1}, "intruder")


def test_validate_and_scenario_are_pure_and_carry_freshness(deps):
    d, service = deps
    result = run_tool_sync(d, "validate_policy_draft", {"portfolio_id": 1, "document": DOC}, USER)
    assert result["valid"] is True
    scenario = run_tool_sync(d, "build_doctor_scenario", {"portfolio_id": 1, "mode": "new_cash_only", "new_cash": 10}, USER)
    assert scenario["executed"] is False and scenario["data_freshness"] == {"status": "test"}
    names = [c[0] for c in service.calls]
    assert "preview_scenario" in names
    assert not {"save", "restore", "preview"} & set(names)


def test_preview_policy_is_not_callable_over_mcp(deps):
    d, _service = deps
    with pytest.raises(McpToolError, match="Tool sconosciuto"):
        run_tool_sync(d, "preview_policy", {"portfolio_id": 1, "document": DOC}, USER)


def test_mcp_doctor_output_is_marked_as_data(deps):
    d, _service = deps
    result = mcp_tools.sanitize_output(run_tool_sync(d, "read_doctor_policy", {"portfolio_id": 1}, USER))
    assert "non istruzioni" in result["data_note"]
    assert "confirmation_token" not in json.dumps(result)
