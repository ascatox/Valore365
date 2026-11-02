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

# --- Historical scenarios: drawdown proxies per asset class (TASK-38) --------
#
# Approvato il 2026-11-02 (TASK-37/38): a historical scenario is "historical"
# only when holdings with real prices in the scenario window (cash included,
# its return is known: 0) cover at least HISTORICAL_MIN_COVERAGE_PCT of the
# portfolio weight; the uncovered part is filled with these class proxies.
# Below the threshold the whole scenario uses the proxies:
#     impact = sum(weight_i x HISTORICAL_CLASS_PROXIES[scenario][class_i])
#
# Values are the approximate total return of a well-known index over the
# scenario window (start -> end of HISTORICAL_SCENARIOS, which roughly runs
# peak -> trough), in percent, rounded to the unit.
# CURRENCY LIMITATION: the indices are quoted in USD. A EUR investor holding
# unhedged instruments saw different numbers (e.g. 2022: MSCI World about -13%
# and gold about +9% in EUR, because the USD rallied). FX effects are not
# modelled; the proxies are an order of magnitude, not the portfolio history.
#
# crypto = None: the class did not exist in the window (Bitcoin trades from
# 2009-2010). The engine then uses the equity proxy (prudential choice) and
# raises the "crypto_pre_inception_equity_proxy" flag.
# "unknown" is not in the table: it takes the equity proxy and raises the
# "unknown_asset_class_equity_proxy" flag.
HISTORICAL_MIN_COVERAGE_PCT = 60.0

HISTORICAL_CLASS_PROXIES: dict[str, dict[str, float | None]] = {
    # 2007-10-01 -> 2009-03-31
    "gfc_2008": {
        "equity": -54.0,     # MSCI World (USD, net): ~-57% Oct-2007 peak to Mar-2009 trough
        "bond": 4.0,         # Bloomberg Global Aggregate (USD unhedged): ~+4/+5%
        "gold": 20.0,        # LBMA gold (USD): ~745 -> ~916 $/oz, ~+23%, rounded down
        "commodity": -45.0,  # Bloomberg Commodity TR (BCOM): ~-45% (peak-to-trough Jul-08/Feb-09 ~-55%)
        "cash": 0.0,
        "crypto": None,      # did not exist
    },
    # 2000-03-01 -> 2002-10-31
    "dotcom_crash": {
        "equity": -47.0,     # MSCI World (USD): ~-49% peak to Oct-2002 trough
        "bond": 18.0,        # Bloomberg Global Aggregate (USD unhedged): ~+18/+20%
        "gold": 8.0,         # LBMA gold (USD): ~293 -> ~317 $/oz
        "commodity": 0.0,    # BCOM TR: +32% 2000, -20% 2001, +26% 2002 -> roughly flat (mixed)
        "cash": 0.0,
        "crypto": None,      # did not exist
    },
    # 2020-02-19 -> 2020-03-23
    "covid_crash": {
        "equity": -34.0,     # MSCI World (USD): ~-34%
        "bond": -3.0,        # Bloomberg Global Aggregate (USD unhedged): ~-3%
        "gold": -3.0,        # LBMA gold (USD): ~1611 -> ~1567 $/oz (intra-window low ~-9%)
        "commodity": -25.0,  # BCOM TR: ~-20/-25% (oil-heavy indices such as GSCI ~-40%)
        "cash": 0.0,
        "crypto": -40.0,     # Bitcoin (USD): ~10.2k -> ~6.5k, intra-window low ~-50%
    },
    # 2022-01-03 -> 2022-10-12
    "bear_market_2022": {
        "equity": -25.0,     # MSCI World (USD): ~-26% (about -13% in EUR)
        "bond": -18.0,       # Bloomberg Global Aggregate (USD unhedged): ~-20%; EUR-hedged ~-13%
        "gold": -5.0,        # LBMA gold (USD): ~1800 -> ~1665 $/oz, ~-7% (about +9% in EUR)
        "commodity": 15.0,   # BCOM TR: ~+15/+20%
        "cash": 0.0,
        "crypto": -58.0,     # Bitcoin (USD): ~46k -> ~19k
    },
}
