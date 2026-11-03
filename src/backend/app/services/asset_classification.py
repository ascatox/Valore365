"""Single asset-class classifier shared by stress, health, X-Ray, long-term
assumptions and income projection (TASK-35, V365-002 / V365-012).

The DB keeps ``assets.asset_type`` as-is (stock/etf/fund/bond/cash/crypto):
an ETC stays typed ``etf`` (or ``stock`` when the provider reports it as
EQUITY) and its asset class is derived here, without schema changes.

Resolution order (first match wins):
1. ``asset_type`` when it is already a class: cash, bond, crypto.
2. ETF enrichment and metadata: justETF ``investment_focus`` /
   ``index_tracked`` and yFinance ``asset_metadata.category`` (source
   ``enrichment``), then the official fund name stored by justETF for the
   ISIN (``etf_enrichment.name``, source ``enrichment_name``).
3. Keywords in the instrument name (source ``name``).
4. Broker abbreviations in the name (source ``name_abbrev``, TASK-50): the
   names stored from broker imports are often short codes such as
   ``XTR2 EGB13 1CC`` (Euro Government Bond) or ``Azioni Europa``. They are
   read only with the explicit tables ``_BOND_ABBREVIATIONS`` /
   ``_EQUITY_ABBREVIATIONS`` and only when one class matches: a name with
   both bond and equity cues stays unresolved.
5. Known symbol / ISIN hints (for instruments stored without a name).
6. Fallback: ``stock`` -> equity (the type itself declares a share), unless
   the name says it is an exchange-traded product (ETC/ETN/ETF), in which case
   the class is ``unknown``; every other type -> ``unknown``.

``unknown`` is never turned into equity here: each consumer decides how to
treat it and says so (approved decision, TASK-37).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

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
    # asset_type | enrichment | enrichment_name | name | name_abbrev | symbol
    # | isin | default | none
    source: str
    # ETF/ETC/ETN/fund-like vehicle (not a single company share).
    is_exchange_traded_product: bool
    # Kind of vehicle (TASK-51): etc | etn | etf | fund | stock | bond |
    # crypto | cash, or None when it cannot be determined. Independent of the
    # asset class: an ETC on gold is instrument_type etc, asset_class gold.
    instrument_type: str | None = None


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
_ETN = _compile((r"\betn\b",))

# Broker abbreviations (TASK-50). Fineco and other brokers store short names
# ("XTR2 EGB13 1CC", "Azioni Europa", "ISH EUR GOVT BD"): the full-name rules
# above do not see them. Each entry is a whole token (word boundaries, digits
# allowed after the code, e.g. EGB13 = Euro Government Bond 1-3y). Words that
# only name a region ("Europa", "Europe", "USA") are deliberately absent: they
# say nothing about the class.
_BOND_ABBREVIATIONS: tuple[str, ...] = (
    r"\begb\d*\b",                 # Euro Government Bond (EGB, EGB13, EGB310)
    r"\beur\s+govt?\b",            # EUR GOV / EUR GOVT
    r"\bgovt?\s*bds?\b",           # GOV BD / GOVT BD / GOVBD
    r"\bgov\b",                     # GOV token
    r"\bgovies\b",
    r"\btreas\b", r"\btrsy\b", r"\btsy\b",
    r"\bcorp\s*bds?\b",            # CORP BD
    r"\bbds?\b",                    # BD token (bond)
    r"\bagg\b",                     # aggregate
    r"\bobbl(?:ig)?\w*",            # obbl, obblig, obbligazionario
    r"titoli\s+di\s+stato",
    r"\binfl\b",                    # inflation-linked
    r"\bbund\b",
    r"\bt-?bills?\b",
)
_EQUITY_ABBREVIATIONS: tuple[str, ...] = (
    r"\bazioni\b",                  # Italian for shares ("Azioni Europa")
    r"\bazion\w*",                  # azionario, azionaria
    r"\beq\b", r"\bequ\b",          # EQ / EQU
    r"\bwrld\b", r"\bwld\b",        # world
    r"\bsp\s?500\b",               # SP500 / SP 500
    r"\bstx\b",                     # STOXX
    r"\bshs\b",                     # shares
)
_BOND_ABBREV = _compile(_BOND_ABBREVIATIONS)
_EQUITY_ABBREV = _compile(_EQUITY_ABBREVIATIONS)

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


def _match_abbreviations(text: str) -> str | None:
    """Bond or equity from broker abbreviations; None when none or both match."""
    is_bond = bool(_BOND_ABBREV.search(text))
    is_equity = bool(_EQUITY_ABBREV.search(text))
    if is_bond == is_equity:
        return None
    return BOND if is_bond else EQUITY


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
    enrichment_name: str | None = None,
) -> AssetClassification:
    """Classify one instrument; see the module docstring for the order."""
    result = _classify(
        asset_type=asset_type, name=name, symbol=symbol, isin=isin,
        investment_focus=investment_focus, index_tracked=index_tracked,
        category=category, enrichment_name=enrichment_name,
    )
    return replace(
        result,
        instrument_type=_instrument_type(
            asset_type=asset_type, name=name, enrichment_name=enrichment_name, isin=isin, result=result,
        ),
    )


def _instrument_type(
    *,
    asset_type: str | None,
    name: str | None,
    enrichment_name: str | None,
    isin: str | None,
    result: AssetClassification,
) -> str | None:
    """Vehicle of the instrument (TASK-51), from the stored type, the name
    tokens (ETC/ETN) and the ISIN hints of physical gold ETCs."""
    normalized_type = (asset_type or "").strip().lower()
    if normalized_type in {CASH, BOND, CRYPTO}:
        return normalized_type
    text = " ".join(part for part in (name, enrichment_name) if part)
    if _ETN.search(text):
        return "etn"
    if _ETC.search(text) or "xetra-gold" in text.lower():
        return "etc"
    if result.asset_class == GOLD and (isin or "").strip().upper() in _ISIN_HINTS:
        return "etc"  # known physical gold ETCs
    if normalized_type in {"etf", "fund"}:
        return normalized_type
    if normalized_type == "stock":
        if result.is_exchange_traded_product:
            # A share whose name/enrichment says ETF/UCITS: a fund vehicle;
            # a commodity without an ETC/ETN token cannot be told apart.
            return None if result.asset_class in {GOLD, COMMODITY} else "etf"
        return "stock"
    return None


def _classify(
    *,
    asset_type: str | None,
    name: str | None,
    symbol: str | None,
    isin: str | None,
    investment_focus: str | None,
    index_tracked: str | None,
    category: str | None,
    enrichment_name: str | None,
) -> AssetClassification:
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
    # Official fund name from justETF for this ISIN: structured data, read
    # with the full-name rules only (no abbreviations needed).
    if enrichment_name and enrichment_name.strip():
        matched = _match_text(enrichment_name)
        if matched:
            return AssetClassification(matched, "enrichment_name", True)

    # A name equal to the symbol carries no information. For a share
    # (asset_type stock) the name is read only when it says the instrument is
    # really an ETC/ETN/ETF: "Barrick Gold" or "Treasury Wine" stay equity.
    name_is_informative = bool(name_text) and name_text.upper() != (symbol or "").strip().upper()
    if name_is_informative and (normalized_type != "stock" or is_etp):
        matched = _match_text(name_text)
        if matched:
            return AssetClassification(matched, "name", is_etp or matched in {GOLD, COMMODITY})
        matched = _match_abbreviations(name_text)
        if matched:
            return AssetClassification(matched, "name_abbrev", is_etp)

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
