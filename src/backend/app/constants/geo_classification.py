"""Geographic classification constants for portfolio analysis."""

REGIONS = ("usa", "europe", "emerging", "other")

GLOBAL_EQUITY_SPLIT = {"usa": 55.0, "europe": 20.0, "emerging": 10.0, "other": 15.0}
GLOBAL_BOND_SPLIT = {"usa": 40.0, "europe": 30.0, "emerging": 5.0, "other": 25.0}

EUROPE_SUFFIXES = (".MI", ".PA", ".AS", ".DE", ".L", ".SW", ".MC", ".BR")
EMERGING_CURRENCIES = {"CNY", "CNH", "INR", "BRL", "MXN", "ZAR", "TWD", "KRW", "IDR", "THB"}
EUROPE_CURRENCIES = {"EUR", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF"}
