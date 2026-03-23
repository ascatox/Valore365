"""Market symbols and news symbols used by the Markets tab."""

MARKET_SYMBOLS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "indices": {
        "label": "Indici",
        "symbols": [
            ("^GSPC", "S&P 500"),
            ("^DJI", "Dow Jones"),
            ("^IXIC", "Nasdaq"),
            ("^STOXX50E", "Euro Stoxx 50"),
            ("FTSEMIB.MI", "FTSE MIB"),
            ("^FTSE", "FTSE 100"),
            ("^GDAXI", "DAX"),
            ("^N225", "Nikkei 225"),
            ("^VIX", "VIX"),
        ],
    },
    "commodities": {
        "label": "Materie Prime",
        "symbols": [
            ("GC=F", "Oro"),
            ("SI=F", "Argento"),
            ("CL=F", "Petrolio WTI"),
        ],
    },
    "crypto": {
        "label": "Criptovalute",
        "symbols": [
            ("BTC-USD", "Bitcoin"),
            ("ETH-USD", "Ethereum"),
            ("SOL-USD", "Solana"),
        ],
    },
}

NEWS_SYMBOLS = ["^GSPC", "^IXIC", "FTSEMIB.MI", "BTC-USD", "GC=F"]
