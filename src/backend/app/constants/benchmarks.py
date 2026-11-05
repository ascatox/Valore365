"""Benchmarks offered by the dashboard comparison chart ("Portafoglio vs ...").

Single source of truth for the ``/benchmarks`` endpoint (which creates the
missing assets on first use) and for the scheduler's daily benchmark backfill.

Symbols are Yahoo Finance symbols (the default ``yfinance`` provider): the
asset is stored with the same symbol and the same provider symbol. The chart
normalises both series to base 100, so the quote currency only matters for
the FX rates fetched alongside the price backfill.
"""

from typing import TypedDict


class BenchmarkDefinition(TypedDict):
    symbol: str
    name: str
    label: str
    quote_currency: str
    exchange_name: str


BENCHMARKS: tuple[BenchmarkDefinition, ...] = (
    {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "label": "S&P 500",
        "quote_currency": "USD",
        "exchange_name": "NYSE Arca",
    },
    {
        "symbol": "QQQ",
        "name": "Invesco QQQ Trust",
        "label": "Nasdaq 100",
        "quote_currency": "USD",
        "exchange_name": "Nasdaq",
    },
    {
        "symbol": "DIA",
        "name": "SPDR Dow Jones Industrial Average ETF Trust",
        "label": "Dow Jones",
        "quote_currency": "USD",
        "exchange_name": "NYSE Arca",
    },
    {
        "symbol": "IWM",
        "name": "iShares Russell 2000 ETF",
        "label": "Russell 2000",
        "quote_currency": "USD",
        "exchange_name": "NYSE Arca",
    },
    {
        # iShares STOXX Europe 600 UCITS ETF (DE), Xetra listing in EUR.
        "symbol": "EXSA.DE",
        "name": "iShares STOXX Europe 600 UCITS ETF (DE)",
        "label": "STOXX Europe 600",
        "quote_currency": "EUR",
        "exchange_name": "XETRA",
    },
)

BENCHMARK_SYMBOLS: tuple[str, ...] = tuple(b["symbol"] for b in BENCHMARKS)
