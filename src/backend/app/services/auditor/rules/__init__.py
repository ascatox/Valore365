"""Regole dell'Auditor, un modulo per gruppo (TASK-74…77).

Ogni modulo espone la lista ``RULES`` di dichiarazioni (``docs/auditor/architecture.md`` §3.2).
Nessun import eager: li importa ``registry.load_rules``, che ignora con un warning un modulo non
ancora presente.
"""

RULE_MODULES: tuple[str, ...] = (
    "stress_classification",   # A, TASK-74
    "rebalance_simulation",    # B, TASK-75
    "costs_income",            # C, TASK-76
    "consistency",             # D, TASK-77
)
