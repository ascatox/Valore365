"""Static data for the Markets tab outlook ("Prossimi giorni sui mercati").

Central bank meeting dates do not come from any market-data provider: the Fed
and the ECB publish them a year or more in advance, so they live here. Add the
following year when the two calendars are published (usually by the summer):
the outlook reports a warning for any day whose year is not covered.

Sources: federalreserve.gov/monetarypolicy/fomccalendars.htm and
ecb.europa.eu/press/calendars/mgcgc. FOMC 2027 dates are still tentative.
"""

from datetime import date

# Each meeting is listed by its decision day (the second day of the meeting);
# True marks the meetings that also publish staff projections (Fed SEP and dot
# plot, ECB/Eurosystem macroeconomic projections).
CENTRAL_BANKS: dict[str, dict] = {
    "fed": {
        "title": "Fed: decisione sui tassi",
        "region": "US",
        "tz": "America/New_York",
        "decision_time": (14, 0),
        "description": (
            "Comunicato FOMC e, mezz'ora dopo, conferenza stampa: orientano tassi USA, "
            "dollaro e valutazioni azionarie globali."
        ),
        "projections_tag": "Proiezioni e dot plot",
        "projections_note": "Riunione con proiezioni economiche e dot plot, di solito la più seguita.",
        "decision_days": {
            date(2026, 1, 28): False,
            date(2026, 3, 18): True,
            date(2026, 4, 29): False,
            date(2026, 6, 17): True,
            date(2026, 7, 29): False,
            date(2026, 9, 16): True,
            date(2026, 10, 28): False,
            date(2026, 12, 9): True,
            date(2027, 1, 27): False,
            date(2027, 3, 17): True,
            date(2027, 4, 28): False,
            date(2027, 6, 9): True,
            date(2027, 7, 28): False,
            date(2027, 9, 15): True,
            date(2027, 10, 27): False,
            date(2027, 12, 8): True,
        },
    },
    "ecb": {
        "title": "BCE: decisione sui tassi",
        "region": "EU",
        "tz": "Europe/Berlin",
        "decision_time": (14, 15),
        "description": (
            "Decisione di politica monetaria e, mezz'ora dopo, conferenza stampa: impatto diretto "
            "su euro, rendimenti dei titoli di Stato (BTP inclusi) e tassi dei mutui."
        ),
        "projections_tag": "Proiezioni macro",
        "projections_note": "Con le nuove proiezioni macroeconomiche su crescita e inflazione.",
        "decision_days": {
            date(2026, 2, 5): False,
            date(2026, 3, 19): True,
            date(2026, 4, 30): False,
            date(2026, 6, 11): True,
            date(2026, 7, 23): False,
            date(2026, 9, 10): True,
            date(2026, 10, 29): False,
            date(2026, 12, 17): True,
            date(2027, 2, 4): False,
            date(2027, 3, 18): True,
            date(2027, 4, 29): False,
            date(2027, 6, 10): True,
            date(2027, 7, 22): False,
            date(2027, 9, 9): True,
            date(2027, 10, 28): False,
            date(2027, 12, 16): True,
        },
    },
}

# Years for which every central bank above has its full schedule.
CENTRAL_BANK_CALENDAR_YEARS: frozenset[int] = frozenset.intersection(
    *(frozenset(d.year for d in bank["decision_days"]) for bank in CENTRAL_BANKS.values())
)

# Companies whose results move the whole market: the largest weights of the
# S&P 500 / Nasdaq and, through them, of global equity ETFs.
BIG_TECH_SYMBOLS: frozenset[str] = frozenset({
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO",
    "ORCL", "NFLX", "AMD", "TSM", "ASML", "SAP", "CRM", "ADBE", "INTC", "QCOM", "PLTR",
})

# Earnings are listed only for companies above this market cap (USD).
EARNINGS_MIN_MARKET_CAP_USD = 100_000_000_000
# ...and are flagged as high impact above this one, even outside BIG_TECH_SYMBOLS.
EARNINGS_HIGH_IMPACT_MARKET_CAP_USD = 500_000_000_000

# Region codes Yahoo uses for the euro area as a whole.
EURO_AREA_REGIONS: frozenset[str] = frozenset({"EZ", "EU", "EA", "EMU", "XM"})

# Economic releases worth showing, matched case-insensitively against the
# release name. Rules are tried in order and the first match wins. Rate
# decisions are not listed: CENTRAL_BANKS already covers them.
MACRO_EVENT_RULES: list[dict] = [
    {
        "key": "us_payrolls",
        "pattern": r"non[- ]?farm payrolls",
        "regions": frozenset({"US"}),
        "title": "Lavoro USA (Non-Farm Payrolls)",
        "description": "Il dato sul lavoro più seguito: sposta le attese sui tassi Fed, il dollaro e i Treasury.",
        "importance": "high",
    },
    {
        "key": "us_cpi",
        "pattern": r"\bcpi\b",
        "regions": frozenset({"US"}),
        "title": "Inflazione USA (CPI)",
        "description": "Un'inflazione sopra le attese allontana i tagli dei tassi e pesa su azioni e obbligazioni.",
        "importance": "high",
    },
    {
        "key": "us_pce",
        "pattern": r"\bpce\b",
        "regions": frozenset({"US"}),
        "title": "Inflazione PCE USA",
        "description": "La misura di inflazione preferita dalla Fed.",
        "importance": "high",
    },
    {
        "key": "us_gdp",
        "pattern": r"\bgdp\b",
        "regions": frozenset({"US"}),
        "title": "PIL USA",
        "description": None,
        "importance": "medium",
    },
    {
        "key": "us_ism",
        "pattern": r"\bism\b",
        "regions": frozenset({"US"}),
        "title": "Indici ISM USA",
        "description": "Fiducia delle imprese: anticipa l'andamento dell'economia.",
        "importance": "medium",
    },
    {
        "key": "us_retail_sales",
        "pattern": r"retail sales",
        "regions": frozenset({"US"}),
        "title": "Vendite al dettaglio USA",
        "description": None,
        "importance": "medium",
    },
    {
        "key": "us_ppi",
        "pattern": r"\bppi\b",
        "regions": frozenset({"US"}),
        "title": "Prezzi alla produzione USA (PPI)",
        "description": None,
        "importance": "medium",
    },
    {
        "key": "fomc_minutes",
        "pattern": r"fomc minutes|fed minutes",
        "regions": frozenset({"US"}),
        "title": "Verbali della Fed",
        "description": "I verbali dell'ultima riunione FOMC: indizi sulle prossime mosse sui tassi.",
        "importance": "medium",
    },
    {
        "key": "ez_inflation",
        "pattern": r"\bhicp\b|\bcpi\b|inflation",
        "regions": EURO_AREA_REGIONS,
        "title": "Inflazione Eurozona",
        "description": "Il dato che guida le decisioni della BCE sui tassi.",
        "importance": "high",
    },
    {
        "key": "ez_gdp",
        "pattern": r"\bgdp\b",
        "regions": EURO_AREA_REGIONS,
        "title": "PIL Eurozona",
        "description": None,
        "importance": "medium",
    },
    {
        "key": "ez_pmi",
        "pattern": r"\bpmi\b",
        "regions": EURO_AREA_REGIONS,
        "title": "PMI Eurozona",
        "description": "Fiducia dei direttori acquisti: anticipa l'andamento dell'economia.",
        "importance": "medium",
    },
    {
        "key": "de_inflation",
        "pattern": r"\bhicp\b|\bcpi\b",
        "regions": frozenset({"DE"}),
        "title": "Inflazione Germania",
        "description": "Esce prima del dato dell'Eurozona e ne anticipa la direzione.",
        "importance": "medium",
    },
    {
        "key": "de_ifo",
        "pattern": r"\bifo\b",
        "regions": frozenset({"DE"}),
        "title": "Fiducia imprese tedesche (Ifo)",
        "description": None,
        "importance": "medium",
    },
    {
        "key": "de_zew",
        "pattern": r"\bzew\b",
        "regions": frozenset({"DE"}),
        "title": "Sentiment economico tedesco (ZEW)",
        "description": None,
        "importance": "medium",
    },
    {
        "key": "it_inflation",
        "pattern": r"\bhicp\b|\bcpi\b",
        "regions": frozenset({"IT"}),
        "title": "Inflazione Italia",
        "description": None,
        "importance": "medium",
    },
    {
        "key": "it_gdp",
        "pattern": r"\bgdp\b",
        "regions": frozenset({"IT"}),
        "title": "PIL Italia",
        "description": None,
        "importance": "medium",
    },
]
