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

SHOCK_SCENARIOS = [
    {
        "id": "global_equity_crash",
        "name": "Global Equity Crash",
        "shocks": {"equity": -0.20, "bond": -0.03, "cash": 0.0},
    },
    {
        "id": "us_tech_crash",
        "name": "US Tech Crash",
        "shocks": {"equity": -0.30, "bond": 0.02, "cash": 0.0},
        "tech_multiplier": 1.5,
    },
    {
        "id": "bond_selloff",
        "name": "Bond Selloff",
        "shocks": {"equity": -0.05, "bond": -0.12, "cash": 0.0},
    },
    {
        "id": "emerging_markets_crisis",
        "name": "Emerging Markets Crisis",
        "shocks": {"equity": -0.25, "bond": -0.08, "cash": 0.0},
    },
    {
        "id": "commodity_drop",
        "name": "Commodity Drop",
        "shocks": {"equity": -0.10, "bond": -0.02, "cash": 0.0},
        "commodity_multiplier": 2.0,
    },
]
