"""Stress test scenarios for the portfolio doctor."""

HISTORICAL_SCENARIOS = [
    {
        "id": "gfc_2008",
        "name": "Global Financial Crisis",
        "period": "2008",
        "start": "2007-10-01",
        "end": "2009-03-31",
        "benchmark_drawdown": -56.8,
    },
    {
        "id": "dotcom_crash",
        "name": "Dot-Com Crash",
        "period": "2000-2002",
        "start": "2000-03-01",
        "end": "2002-10-31",
        "benchmark_drawdown": -49.1,
    },
    {
        "id": "covid_crash",
        "name": "Covid Crash",
        "period": "Feb-Mar 2020",
        "start": "2020-02-19",
        "end": "2020-03-23",
        "benchmark_drawdown": -33.9,
    },
    {
        "id": "bear_market_2022",
        "name": "Bear Market 2022",
        "period": "2022",
        "start": "2022-01-03",
        "end": "2022-10-12",
        "benchmark_drawdown": -25.4,
    },
]

# Shock per asset class of the shared classifier
# (app/services/asset_classification.py). Every class except "unknown" has an
# explicit value: non-equity classes no longer fall back to the equity shock.
# "unknown" instruments get the equity shock as a prudential choice and the
# scenario result carries the "unknown_asset_class_equity_shock" flag.
#
# Approvati il 2026-11-02 (TASK-37): the gold, commodity and crypto shocks
# (and the gold shock in the bond selloff) are deliberately
# conservative values reasoned from historical behaviour:
# - Dot-com crash 2000-2002: gold roughly flat to up, broad commodities mixed
#   -> tech crash: gold 0%, commodity -10%.
# - GFC 2008: commodities -50% peak to trough, gold -25% intra-year but up on
#   the year -> global equity crash: gold -5%, commodity -15%.
# - 2013 taper tantrum / 2022: rising real rates hit gold (-28% in 2013, about
#   flat in USD in 2022) -> bond selloff: gold -10%, commodity -5%.
# - EM crises (1997-98): commodities fell sharply, gold slightly down
#   -> EM crisis: gold -5%, commodity -15%.
# - Commodity drop (2014-15): broad commodities -25/-30%, gold about -10%
#   -> commodity drop: gold -10%, commodity -20% (the old 2x multiplier on -10%).
# - Crypto: drawdowns about 1.5-2x equity -> -35/-45/-10/-30/-10%.
SHOCK_SCENARIOS = [
    {
        "id": "global_equity_crash",
        "name": "Global Equity Crash",
        "shocks": {
            "equity": -0.20, "bond": -0.03, "cash": 0.0,
            "gold": -0.05, "commodity": -0.15, "crypto": -0.35,
        },
    },
    {
        "id": "us_tech_crash",
        "name": "US Tech Crash",
        "shocks": {
            "equity": -0.30, "bond": 0.02, "cash": 0.0,
            "gold": 0.0, "commodity": -0.10, "crypto": -0.45,
        },
        # Applied to tech-like equity holdings only.
        "tech_multiplier": 1.5,
    },
    {
        "id": "bond_selloff",
        "name": "Bond Selloff",
        "shocks": {
            "equity": -0.05, "bond": -0.12, "cash": 0.0,
            "gold": -0.10, "commodity": -0.05, "crypto": -0.10,
        },
    },
    {
        "id": "emerging_markets_crisis",
        "name": "Emerging Markets Crisis",
        "shocks": {
            "equity": -0.25, "bond": -0.08, "cash": 0.0,
            "gold": -0.05, "commodity": -0.15, "crypto": -0.30,
        },
    },
    {
        "id": "commodity_drop",
        "name": "Commodity Drop",
        "shocks": {
            "equity": -0.10, "bond": -0.02, "cash": 0.0,
            "gold": -0.10, "commodity": -0.20, "crypto": -0.10,
        },
    },
]
