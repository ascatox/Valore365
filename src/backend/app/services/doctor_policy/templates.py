"""Illustrative policy templates (Bilanciato, Prudente, Dinamico, vuoto).

They are starting points for writing *one's own* rules: examples of how the
rules are written, not recommendations, not an assessment of suitability for
anyone. The user edits them and confirms every saved version.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .validator import normalize_policy_document

TEMPLATE_VERSION = "2026-11-04.1"
TEMPLATE_DISCLAIMER = (
    "Esempio illustrativo per scrivere le tue regole: non è una raccomandazione né una "
    "valutazione di adeguatezza. Modifica le soglie secondo le tue scelte."
)


def _rule(rule_id: str, metric_code: str, operator: str, *, min_value=None, max_value=None, severity="medium", precision=None, label=None) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "rule_id": rule_id,
        "metric_code": metric_code,
        "operator": operator,
        "min_value": min_value,
        "max_value": max_value,
        "severity": severity,
    }
    if precision is not None:
        rule["precision"] = precision
    if label:
        rule["label"] = label
    return rule


_TEMPLATES: list[dict[str, Any]] = [
    {
        "template_id": "bilanciato",
        "name": "Bilanciato (esempio)",
        "description": "Esempio di regole per un mix azioni/obbligazioni con limiti di concentrazione e costo.",
        "rules": [
            _rule("equity-range", "equity_weight_pct", "range", min_value=50.0, max_value=70.0, severity="high"),
            _rule("bond-range", "bond_weight_pct", "range", min_value=25.0, max_value=45.0),
            _rule("gold-max", "gold_weight_pct", "max", max_value=10.0, severity="low"),
            _rule("max-single", "max_single_position_pct", "max", max_value=40.0, severity="high"),
            _rule("top3-max", "top3_positions_pct", "max", max_value=80.0),
            _rule("usa-max", "usa_exposure_pct", "max", max_value=60.0),
            _rule("ter-max", "weighted_ter_pct", "max", max_value=0.4, precision=2, severity="low"),
            _rule("overlap-max", "etf_overlap_pct", "max", max_value=60.0, severity="low"),
        ],
    },
    {
        "template_id": "prudente",
        "name": "Prudente (esempio)",
        "description": "Esempio di regole con quota azionaria contenuta e prevalenza obbligazionaria.",
        "rules": [
            _rule("equity-max", "equity_weight_pct", "max", max_value=40.0, severity="high"),
            _rule("bond-min", "bond_weight_pct", "min", min_value=50.0, severity="high"),
            _rule("gold-max", "gold_weight_pct", "max", max_value=10.0, severity="low"),
            _rule("max-single", "max_single_position_pct", "max", max_value=35.0),
            _rule("usa-max", "usa_exposure_pct", "max", max_value=50.0, severity="low"),
            _rule("ter-max", "weighted_ter_pct", "max", max_value=0.4, precision=2, severity="low"),
        ],
    },
    {
        "template_id": "dinamico",
        "name": "Dinamico (esempio)",
        "description": "Esempio di regole con quota azionaria elevata e limiti su concentrazione ed esposizione USA.",
        "rules": [
            _rule("equity-min", "equity_weight_pct", "min", min_value=75.0, severity="high"),
            _rule("max-single", "max_single_position_pct", "max", max_value=50.0, severity="high"),
            _rule("top3-max", "top3_positions_pct", "max", max_value=90.0),
            _rule("usa-max", "usa_exposure_pct", "max", max_value=70.0),
            _rule("ter-max", "weighted_ter_pct", "max", max_value=0.5, precision=2, severity="low"),
            _rule("overlap-max", "etf_overlap_pct", "max", max_value=70.0, severity="low"),
        ],
    },
    {
        "template_id": "vuoto",
        "name": "Inizia da zero",
        "description": "Nessuna regola: aggiungi tu i limiti che vuoi monitorare.",
        "rules": [],
    },
]


def list_templates() -> list[dict[str, Any]]:
    """Templates in the ``TemplateRead`` shape, documents normalized."""
    out = []
    for template in _TEMPLATES:
        out.append({
            "template_id": template["template_id"],
            "name": template["name"],
            "description": template["description"],
            "template_version": TEMPLATE_VERSION,
            "illustrative": True,
            "disclaimer": TEMPLATE_DISCLAIMER,
            "document": normalize_policy_document({"schema_version": 1, "rules": deepcopy(template["rules"])}),
        })
    return out


def get_template(template_id: str) -> dict[str, Any] | None:
    for template in list_templates():
        if template["template_id"] == template_id:
            return template
    return None
