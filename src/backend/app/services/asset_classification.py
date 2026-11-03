"""Single asset-class classifier shared by stress, health, X-Ray, long-term
assumptions and income projection (TASK-35, V365-002 / V365-012).

The DB keeps ``assets.asset_type`` as-is (stock/etf/fund/bond/cash/crypto):
an ETC stays typed ``etf`` (or ``stock`` when the provider reports it as
EQUITY) and its asset class is derived here, without schema changes.

Resolution order (first match wins):
1. ``asset_type`` when it is already a class: cash, bond, crypto.
2. ETF enrichment and metadata: justETF ``investment_focus`` /
   ``index_tracked`` and yFinance ``asset_metadata.category``.
3. Keywords in the instrument name.
4. Known symbol / ISIN hints (for instruments stored without a name).
5. Fallback: ``stock`` -> equity (the type itself declares a share), unless
   the name says it is an exchange-traded product (ETC/ETN/ETF), in which case
   the class is ``unknown``; every other type -> ``unknown``.

``unknown`` is never turned into equity here: each consumer decides how to
treat it and says so (approved decision, TASK-37).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EQUITY = "equity"
BOND = "bond"
GOLD = "gold"
COMMODITY = "commodity"
CASH = "cash"
CRYPTO = "crypto"
UNKNOWN = "unknown"

ASSET_CLASSES: tuple[str, ...] = (EQUITY, BOND, GOLD, COMMODITY, CASH, CRYPTO, UNKNOWN)


@dataclass(frozen=True)
class AssetClassification:
    asset_class: str
    # asset_type | enrichment | name | symbol | isin | default | none
    source: str
    # ETF/ETC/ETN/fund-like vehicle (not a single company share).
    is_exchange_traded_product: bool


def _compile(patterns: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile("|".join(patterns), re.IGNORECASE)


# Equity funds whose description mentions a commodity (gold miners, energy
# producers): checked first so they are not taken for the commodity itself.
_EQUITY_OVERRIDE = _compile((
    r"\bminers?\b", r"\bmining\b", r"\bproducers?\b", r"equity precious metals",
))
_CRYPTO = _compile((r"bitcoin", r"ethereum", r"\bcrypto", r"digital assets?"))
_CASH = _compile((
    r"money market", r"\bmonetari", r"overnight rate", r"€str", r"\bester\b", r"\beonia\b",
))
_GOLD = _compile((r"\bgold\b", r"\boro\b", r"\bxau\b"))
_COMMODITY = _compile((
    r"commodit", r"materie prime", r"precious metals?", r"\bsilver\b", r"\bargento\b",
    r"\bplatinum\b", r"\bpalladium\b", r"crude", r"\boil\b", r"\bbrent\b", r"\bwti\b",
    r"natural gas", r"\bcopper\b", r"agricultur",
))
_BOND = _compile((
    r"\bbonds?\b", r"obbligaz", r"fixed income", r"treasur", r"\bgovt\b", r"government",
    r"aggregate", r"high yield", r"inflation[- ]linked", r"inflation[- ]protected",
    r"\btips\b", r"\bgilts?\b", r"\bbtp\b", r"sovereign", r"ftse mts",
))
_EQUITY = _compile((
    r"equity", r"azionar", r"\bstocks?\b", r"\bmsci\b", r"s&p", r"\bftse\b", r"stoxx",
    r"nasdaq", r"\bdax\b", r"russell", r"dow jones", r"nikkei", r"\bworld\b", r"all-world",
    r"\bacwi\b", r"dividend", r"small cap", r"large cap", r"mid cap", r"\breit", r"real estate",
    r"blend", r"growth", r"\bvalue\b", r"technology",
))
_ETP = _compile((
    r"\betf\b", r"\betc\b", r"\betn\b", r"\bucits\b", r"\bfund\b", r"\bfondo\b",
    r"\bphysical\b", r"xetra-gold",
))
_ETC = _compile((r"\betc\b",))

# Known listings stored without a meaningful name (base symbol, exchange
# suffix stripped). Kept short on purpose: names and enrichment come first.
_SYMBOL_HINTS: dict[str, str] = {
    # gold
    "GLD": GOLD, "IAU": GOLD, "SGLD": GOLD, "PHAU": GOLD, "XAD1": GOLD, "4GLD": GOLD,
    "EGLN": GOLD, "IGLN": GOLD, "SGOL": GOLD, "GBS": GOLD, "XGLD": GOLD,
    # other commodities
    "SLV": COMMODITY, "PHAG": COMMODITY, "DBC": COMMODITY, "CMOD": COMMODITY, "PDBC": COMMODITY,
    # bonds
    "TLT": BOND, "IEF": BOND, "SHY": BOND, "AGG": BOND, "BND": BOND, "LQD": BOND, "HYG": BOND,
    "TIP": BOND, "AGGH": BOND, "IHYG": BOND, "FRC3": BOND, "IBTM": BOND, "IBGL": BOND,
    "VAGF": BOND, "XGLE": BOND, "EUNA": BOND, "XGSH": BOND,
    # crypto
    "BTC": CRYPTO, "ETH": CRYPTO,
}

_ISIN_HINTS: dict[str, str] = {
    "DE000A1EK0G3": GOLD,  # Xtrackers IE Physical Gold ETC
    "DE000A0S9GB0": GOLD,  # Xetra-Gold
    "IE00B4ND3602": GOLD,  # iShares Physical Gold ETC
    "JE00B1VS3770": GOLD,  # WisdomTree Physical Gold
    "DE000A0H0728": COMMODITY,  # iShares Diversified Commodity Swap
}


def _match_text(text: str) -> str | None:
    if not text.strip():
        return None
    if _EQUITY_OVERRIDE.search(text):
        return EQUITY
    for pattern, asset_class in (
        (_CRYPTO, CRYPTO),
        (_CASH, CASH),
        (_GOLD, GOLD),
        (_COMMODITY, COMMODITY),
        (_BOND, BOND),
        (_EQUITY, EQUITY),
    ):
        if pattern.search(text):
            return asset_class
    return None


def _base_symbol(symbol: str) -> str:
    return symbol.strip().upper().split(".")[0]


def classify_asset(
    *,
    asset_type: str | None = None,
    name: str | None = None,
    symbol: str | None = None,
    isin: str | None = None,
    investment_focus: str | None = None,
    index_tracked: str | None = None,
    category: str | None = None,
) -> AssetClassification:
    """Classify one instrument; see the module docstring for the order."""
    normalized_type = (asset_type or "").strip().lower()
    name_text = (name or "").strip()
    is_etp = normalized_type in {"etf", "fund"} or bool(_ETP.search(name_text))

    if normalized_type in {CASH, BOND, CRYPTO}:
        return AssetClassification(normalized_type, "asset_type", is_etp)
    if normalized_type == COMMODITY:
        return AssetClassification(COMMODITY, "asset_type", True)

    enrichment_text = " ".join(part for part in (investment_focus, index_tracked, category) if part)
    matched = _match_text(enrichment_text)
    if matched:
        return AssetClassification(matched, "enrichment", is_etp)

    # A name equal to the symbol carries no information. For a share
    # (asset_type stock) the name is read only when it says the instrument is
    # really an ETC/ETN/ETF: "Barrick Gold" or "Treasury Wine" stay equity.
    name_is_informative = bool(name_text) and name_text.upper() != (symbol or "").strip().upper()
    if name_is_informative and (normalized_type != "stock" or is_etp):
        matched = _match_text(name_text)
        if matched:
            return AssetClassification(matched, "name", is_etp or matched in {GOLD, COMMODITY})

    if symbol:
        matched = _SYMBOL_HINTS.get(_base_symbol(symbol))
        if matched:
            return AssetClassification(matched, "symbol", is_etp or matched in {GOLD, COMMODITY, BOND})
    if isin:
        matched = _ISIN_HINTS.get(isin.strip().upper())
        if matched:
            return AssetClassification(matched, "isin", True)

    # An ETC with no recognizable underlying is still a commodity product.
    if _ETC.search(name_text):
        return AssetClassification(COMMODITY, "name", True)
    if normalized_type == "stock" and not is_etp:
        return AssetClassification(EQUITY, "default", False)
    return AssetClassification(UNKNOWN, "none", is_etp)


def classify_asset_class(**kwargs) -> str:
    return classify_asset(**kwargs).asset_class
