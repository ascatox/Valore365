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

# Google News searches (Italian) for the headlines, with the market they are
# shown under: the main exchanges of each region, commodities and crypto.
NEWS_QUERIES: list[tuple[str, str]] = [
    ("Wall Street", "USA"),
    ("borse europee", "Europa"),
    ("Piazza Affari", "Italia"),
    ("borse asiatiche OR Nikkei", "Asia"),
    ("prezzo petrolio OR prezzo oro", "Materie prime"),
    ("bitcoin", "Crypto"),
]

# Symbols whose Yahoo news are added when Google News returns too few headlines.
NEWS_SYMBOLS: list[tuple[str, str]] = [
    ("^GSPC", "USA"),
    ("^IXIC", "USA"),
    ("^STOXX50E", "Europa"),
    ("^GDAXI", "Europa"),
    ("FTSEMIB.MI", "Italia"),
    ("^N225", "Asia"),
    ("GC=F", "Materie prime"),
    ("CL=F", "Materie prime"),
    ("BTC-USD", "Crypto"),
]
