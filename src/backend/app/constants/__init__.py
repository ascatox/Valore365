"""Application constants — re-exported for convenience."""

from .market_symbols import MARKET_SYMBOLS, NEWS_SYMBOLS
from .stress_scenarios import HISTORICAL_SCENARIOS, SHOCK_SCENARIOS
from .geo_classification import (
    REGIONS,
    GLOBAL_EQUITY_SPLIT,
    GLOBAL_BOND_SPLIT,
    EUROPE_SUFFIXES,
    EMERGING_CURRENCIES,
    EUROPE_CURRENCIES,
)

__all__ = [
    "MARKET_SYMBOLS",
    "NEWS_SYMBOLS",
    "HISTORICAL_SCENARIOS",
    "SHOCK_SCENARIOS",
    "REGIONS",
    "GLOBAL_EQUITY_SPLIT",
    "GLOBAL_BOND_SPLIT",
    "EUROPE_SUFFIXES",
    "EMERGING_CURRENCIES",
    "EUROPE_CURRENCIES",
]
