"""Doctor 2.0 policy documents: strict validation, normalization, hash, diff."""

import pytest

from app.services.doctor_policy import (
    METRIC_REGISTRY,
    PolicyValidationError,
    diff_documents,
    document_hash,
    list_templates,
    normalize_policy_document,
    validate_policy_document,
)


def _rule(**overrides):
    rule = {
        "rule_id": "max-single",
        "metric_code": "max_single_position_pct",
        "operator": "max",
        "max_value": 35,
    }
    rule.update(overrides)
    return rule


def _codes(errors):
    return {(e.field, e.code) for e in errors}


def test_empty_document_is_valid_and_normalized():
    assert validate_policy_document({"schema_version": 1, "rules": []}) == []
    assert validate_policy_document({}) == []
    assert normalize_policy_document({}) == {"schema_version": 1, "rules": []}


def test_normalization_fills_defaults_and_floats():
    doc = normalize_policy_document({"rules": [_rule()]})
    rule = doc["rules"][0]
    assert rule == {
        "rule_id": "max-single",
        "metric_code": "max_single_position_pct",
        "operator": "max",
        "min_value": None,
        "max_value": 35.0,
        "unit": "pct",
        "precision": 1,
        "severity": "medium",
        "warning_margin": 2.0,
        "min_coverage_pct": 80.0,
        "max_data_age_days": 5,
        "enabled": True,
        "label": None,
    }
    assert isinstance(rule["max_value"], float)


def test_ter_rule_defaults_use_registry_margin_and_precision():
    doc = normalize_policy_document({"rules": [_rule(rule_id="ter", metric_code="weighted_ter_pct", max_value=0.3)]})
    assert doc["rules"][0]["warning_margin"] == METRIC_REGISTRY["weighted_ter_pct"].default_warning_margin
    assert doc["rules"][0]["precision"] == 2


def test_infeasible_minimums_55_50_10():
    doc = {"rules": [
        _rule(rule_id="eq", metric_code="equity_weight_pct", operator="min", max_value=None, min_value=55),
        _rule(rule_id="bd", metric_code="bond_weight_pct", operator="min", max_value=None, min_value=50),
        _rule(rule_id="gd", metric_code="gold_weight_pct", operator="range", min_value=10, max_value=15),
    ]}
    errors = validate_policy_document(doc)
    assert ("rules", "infeasible") in _codes(errors)
    assert "115%" in next(e.message for e in errors if e.code == "infeasible")


def test_minimums_summing_to_100_are_feasible():
    doc = {"rules": [
        _rule(rule_id="eq", metric_code="equity_weight_pct", operator="min", max_value=None, min_value=60),
        _rule(rule_id="bd", metric_code="bond_weight_pct", operator="min", max_value=None, min_value=40),
    ]}
    assert validate_policy_document(doc) == []


def test_disabled_rules_do_not_make_a_document_infeasible():
    doc = {"rules": [
        _rule(rule_id="eq", metric_code="equity_weight_pct", operator="min", max_value=None, min_value=80),
        _rule(rule_id="bd", metric_code="bond_weight_pct", operator="min", max_value=None, min_value=50, enabled=False),
    ]}
    assert validate_policy_document(doc) == []


def test_top3_max_below_single_max_is_rejected():
    doc = {"rules": [
        _rule(max_value=40),
        _rule(rule_id="top3", metric_code="top3_positions_pct", max_value=30),
    ]}
    assert ("rules[1].max_value", "inconsistent") in _codes(validate_policy_document(doc))


def test_unknown_metric_operator_and_unit():
    errors = validate_policy_document({"rules": [
        _rule(metric_code="sharpe_ratio"),
        _rule(rule_id="b", metric_code="top3_positions_pct", operator="min", max_value=None, min_value=10),
        _rule(rule_id="c", metric_code="equity_weight_pct", unit="eur"),
        _rule(rule_id="d", metric_code="bond_weight_pct", operator="between"),
    ]})
    codes = _codes(errors)
    assert ("rules[0].metric_code", "unknown_metric") in codes
    assert ("rules[1].operator", "operator_not_allowed") in codes
    assert ("rules[2].unit", "invalid_unit") in codes
    assert ("rules[3].operator", "invalid_operator") in codes


def test_required_thresholds_and_ranges():
    codes = _codes(validate_policy_document({"rules": [
        _rule(max_value=None),
        _rule(rule_id="r", metric_code="equity_weight_pct", operator="range", min_value=70, max_value=50),
        _rule(rule_id="m", metric_code="bond_weight_pct", operator="min", max_value=10, min_value=5),
        _rule(rule_id="o", metric_code="gold_weight_pct", max_value=101),
        _rule(rule_id="n", metric_code="usa_exposure_pct", max_value=-1),
    ]}))
    assert ("rules[0].max_value", "required") in codes
    assert ("rules[1].min_value", "min_gt_max") in codes
    assert ("rules[2].max_value", "not_allowed") in codes
    assert ("rules[3].max_value", "out_of_range") in codes
    assert ("rules[4].max_value", "out_of_range") in codes


def test_inclusive_value_bounds_0_and_100_are_valid():
    assert validate_policy_document({"rules": [
        _rule(rule_id="a", metric_code="equity_weight_pct", operator="range", min_value=0, max_value=100),
    ]}) == []


def test_numbers_must_be_numbers_no_strings_no_expressions():
    codes = _codes(validate_policy_document({"rules": [
        _rule(max_value="35"),
        _rule(rule_id="b", metric_code="top3_positions_pct", max_value="__import__('os')"),
        _rule(rule_id="c", metric_code="bond_weight_pct", operator="max", max_value=True),
        _rule(rule_id="d", metric_code="gold_weight_pct", max_value=float("nan")),
    ]}))
    assert ("rules[0].max_value", "invalid_type") in codes
    assert ("rules[1].max_value", "invalid_type") in codes
    assert ("rules[2].max_value", "invalid_type") in codes
    assert ("rules[3].max_value", "invalid_type") in codes


@pytest.mark.parametrize("precision, ok", [(0, True), (3, True), (4, False), (-1, False), (1.5, False), ("1", False)])
def test_precision_0_to_3(precision, ok):
    errors = validate_policy_document({"rules": [_rule(precision=precision)]})
    assert (errors == []) is ok
    if not ok:
        assert errors[0].field == "rules[0].precision"


def test_extra_fields_rejected_at_both_levels():
    codes = _codes(validate_policy_document({"rules": [_rule(expression="x > 3")], "owner": "me"}))
    assert ("owner", "extra_field") in codes
    assert ("rules[0].expression", "extra_field") in codes


def test_max_20_rules():
    rules = [_rule(rule_id=f"r{i}") for i in range(21)]
    assert ("rules", "too_many_rules") in _codes(validate_policy_document({"rules": rules}))


def test_unique_rule_id_and_metric_code():
    codes = _codes(validate_policy_document({"rules": [
        _rule(),
        _rule(rule_id="max-single", metric_code="top3_positions_pct", max_value=80),
        _rule(rule_id="other"),
    ]}))
    assert ("rules[1].rule_id", "duplicate") in codes
    assert ("rules[2].metric_code", "duplicate") in codes


@pytest.mark.parametrize("rule_id", ["", "Max", "-a", "a" * 41, "a b", 12])
def test_rule_id_format(rule_id):
    assert validate_policy_document({"rules": [_rule(rule_id=rule_id)]})[0].field == "rules[0].rule_id"


def test_other_field_checks():
    codes = _codes(validate_policy_document({"rules": [
        _rule(severity="critical", enabled="yes", label="x" * 81, max_data_age_days=0, min_coverage_pct=120),
    ], "schema_version": 2}))
    assert ("schema_version", "unsupported_version") in codes
    assert ("rules[0].severity", "invalid_value") in codes
    assert ("rules[0].enabled", "invalid_type") in codes
    assert ("rules[0].label", "too_long") in codes
    assert ("rules[0].max_data_age_days", "out_of_range") in codes
    assert ("rules[0].min_coverage_pct", "out_of_range") in codes


def test_not_a_document():
    assert validate_policy_document([1, 2])[0].code == "invalid_type"
    assert validate_policy_document({"rules": "x"})[0].field == "rules"
    with pytest.raises(PolicyValidationError) as excinfo:
        normalize_policy_document({"rules": [_rule(max_value=None)]})
    assert excinfo.value.errors[0].field == "rules[0].max_value"


def test_document_hash_is_canonical():
    a = {"schema_version": 1, "rules": [_rule(max_value=35)]}
    b = {"rules": [{**_rule(max_value=35.0), "severity": "medium", "enabled": True}], "schema_version": 1}
    assert document_hash(a) == document_hash(b)
    assert len(document_hash(a)) == 64
    assert document_hash(a) != document_hash({"rules": [_rule(max_value=36)]})


def test_diff_documents():
    before = {"rules": [_rule(), _rule(rule_id="usa", metric_code="usa_exposure_pct", max_value=60)]}
    after = {"rules": [
        _rule(max_value=30),
        _rule(rule_id="ter", metric_code="weighted_ter_pct", max_value=0.3),
    ]}
    diff = diff_documents(before, after)
    assert [(d["rule_id"], d["change"]) for d in diff] == [
        ("max-single", "modified"), ("ter", "added"), ("usa", "removed"),
    ]
    assert diff[0]["before"]["max_value"] == 35.0 and diff[0]["after"]["max_value"] == 30.0
    assert diff_documents(None, before)[0]["change"] == "added"
    assert diff_documents(before, before) == []


def test_templates_are_valid_illustrative_and_versioned():
    templates = list_templates()
    ids = [t["template_id"] for t in templates]
    assert ids == ["bilanciato", "prudente", "dinamico", "vuoto"]
    for t in templates:
        assert t["illustrative"] is True
        assert "non è una raccomandazione" in t["disclaimer"]
        assert t["template_version"]
        assert validate_policy_document(t["document"]) == []
    assert templates[-1]["document"]["rules"] == []


# -- hardening: huge integers, rule_id anchoring ----------------------------------


@pytest.mark.parametrize("field", ["max_value", "warning_margin", "min_coverage_pct"])
@pytest.mark.parametrize("value", [10**400, -(10**400)], ids=["huge", "huge-negative"])
def test_huge_integer_is_a_field_error_not_overflow(field, value):
    errors = validate_policy_document({"schema_version": 1, "rules": [_rule(**{field: value})]})
    assert (f"rules[0].{field}", "out_of_range") in _codes(errors)


@pytest.mark.parametrize("rule_id", ["max-single\n", "max-single\r\n", "\nmax-single", "a" * 41])
def test_rule_id_trailing_newline_is_rejected(rule_id):
    errors = validate_policy_document({"schema_version": 1, "rules": [_rule(rule_id=rule_id)]})
    assert ("rules[0].rule_id", "invalid_format") in _codes(errors)


def test_rule_schema_pattern_rejects_trailing_newline():
    from pydantic import ValidationError

    from app.schemas.doctor_policy import PolicyRule

    with pytest.raises(ValidationError):
        PolicyRule.model_validate({**_rule(), "rule_id": "max-single\n", "unit": "pct"})
