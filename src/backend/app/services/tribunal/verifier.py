"""Deterministic verifier of the Tribunale (contract ``docs/tribunale/api-contracts.md`` §7).

Pure functions: no network, database, clock, configuration or logging. Given the raw
structured answer of the model and the case file, they return the admitted items in their
verified form (§6) and, for the discarded ones, only ``(path, code)``. The discarded text
never leaves this module.

Every item is checked on its own and gets the **first** discard code in the precedence order
of §7.3 (``DISCARD_CODES``), or is admitted.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from ...copilot_doctor_tools import clean_text

# ---------------------------------------------------------------------------
# Constants (api-contracts §1, §7.3)
# ---------------------------------------------------------------------------

DISCARD_CODES: tuple[str, ...] = (
    "schema_non_valido",
    "riferimento_non_ammesso",
    "nessun_fatto",
    "troppi_fatti",
    "fatto_inesistente",
    "fatto_non_citabile",
    "segnaposto_malformato",
    "segnaposto_non_citato",
    "fatto_estraneo",
    "testo_troppo_lungo",
    "strumento_non_ammesso",
    "cifra_libera",
    "indicazione_operativa",
    "verdetto",
    "troppi_argomenti",
)

MAX_ARGUMENTS_PER_VOICE = 4
MAX_REBUTTALS_PER_VOICE = 2
MAX_FACTS_PER_ITEM = 4
MIN_TEXT_CHARS = 20
MAX_ARGUMENT_CHARS = 360
MAX_REBUTTAL_CHARS = 280
MAX_POINT_CHARS = 300
MAX_SIDE_CHARS = 240
MAX_QUESTION_CHARS = 200
MAX_SHARED_POINTS = 3
MAX_CONTESTED_POINTS = 3
MAX_OPEN_QUESTIONS = 3

VOICE_CODES: dict[str, str] = {"indicizzatore": "IND", "fattoriale": "FAT", "prudente": "PRU"}
VOICE_ORDER: tuple[str, ...] = ("indicizzatore", "fattoriale", "prudente")

THEMES: frozenset[str] = frozenset({
    "costi", "diversificazione", "concentrazione", "composizione", "esposizione_geografica",
    "esposizione_settoriale", "rischio", "scenari", "regole_personali", "qualita_dati",
})
ARGUMENT_STANCES: frozenset[str] = frozenset({"punto_di_forza", "criticita", "neutro"})
REBUTTAL_STANCES: frozenset[str] = frozenset({"concorda", "contesta", "precisa"})

# §7.2
PLACEHOLDER_RE = re.compile(r"\{F([1-9][0-9]{0,2})\}")

# §7.4
YEAR_RE = re.compile(r"(?<![0-9])(19|20)[0-9]{2}(?![0-9])")
FREE_SYMBOLS: frozenset[str] = frozenset("%‰€$£¥")
WORD_RE = re.compile(r"[^\W\d_]+")
QUANTITY_WORDS: frozenset[str] = frozenset({
    "metà", "doppio", "doppia", "doppi", "doppie", "triplo", "tripla", "decina", "decine",
    "dozzina", "dozzine", "centinaio", "centinaia", "migliaio", "migliaia", "milione", "milioni",
    "miliardo", "miliardi", "percento",
})
ALLOWED_NUMERALS: frozenset[str] = frozenset({"un", "uno", "una", "due", "tre", "tré", "sei"})

_U = r"(?:uno|un|una|due|tre|tré|quattro|cinque|sei|sette|otto|nove)"
_T = (r"(?:dieci|undici|dodici|tredici|quattordici|quindici|sedici|diciassette|diciotto"
      r"|diciannove)")
_D = (r"(?:venti|vent|trenta|trent|quaranta|quarant|cinquanta|cinquant|sessanta|sessant"
      r"|settanta|settant|ottanta|ottant|novanta|novant)")
_S100 = rf"(?:{_T}|{_D}{_U}?|{_U})"
_C = rf"(?:(?:due|tre|quattro|cinque|sei|sette|otto|nove)?cento{_S100}?)"
_S1000 = rf"(?:{_C}|{_S100})"
NUMERAL_RE = re.compile(rf"(?:mille{_S1000}?|{_S1000}mila{_S1000}?|{_S1000})")

# §7.5
ISIN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}[A-Z0-9]{9}[0-9](?![A-Z0-9])")
TICKER_RE = re.compile(r"(?<![\w.])[A-Z][A-Z0-9]{1,5}(?:\.[A-Z]{1,3})?(?![\w])")
ALLOWED_ACRONYMS: frozenset[str] = frozenset({
    "ETF", "ETC", "ETN", "ETP", "TER", "OICR", "UCITS", "KID", "ESG", "REIT", "PAC", "ISIN",
    "IPO", "USA", "UE", "UK", "EM", "EUR", "USD", "GBP", "CHF", "JPY", "PIL", "BCE", "FED",
    "IVA", "MSCI", "FTSE", "STOXX", "NASDAQ", "NYSE", "DAX", "BTP", "BOT", "CCT", "AI", "IA",
})
ISSUER_BRANDS: tuple[str, ...] = (
    "ishares", "vanguard", "xtrackers", "amundi", "lyxor", "spdr", "invesco", "wisdomtree",
    "vaneck", "hsbc", "ubs", "franklin", "jpmorgan", "j.p. morgan", "fidelity", "blackrock",
    "pimco", "dws", "bnp paribas", "deka", "legal & general", "l&g", "global x", "hanetf",
    "state street", "schwab", "ossiam", "fineco", "eurizon", "anima", "arca",
)
_ISSUER_RES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])")) for name in ISSUER_BRANDS
)

# §7.6
OPERATIVE_RE = re.compile(
    r"\b(?:compr(?:a|are|ate|i|iamo|ino|ando|erei|eresti|erebbe|erebbero)"
    r"|acquist(?:a|are|ate|i|iamo|ino|ando|erei|eresti|erebbe|erebbero)"
    r"|vend(?:i|ere|ete|iamo|a|ano|endo|erei|eresti|erebbe|erebbero)"
    r"|disinvest(?:i|ire|ite|iamo|a|ano|endo|irei|iresti|irebbe)"
    r"|liquid(?:are|ate|iamo|ando|erei|erebbe)"
    r"|sostitu(?:isci|ire|ite|iamo|isca|endo|irei|irebbe)"
    r"|allegger(?:isci|ire|ite|endo|irei|irebbe)"
    r"|ribilanci(?:a|are|ate|ando|erei|erebbe)"
    r"|switch(?:are)?"
    r"|consigli\w*|raccomand\w*|dovrest[ei]|devi|dovete|adeguat\w*|mifid)\b")

# §7.7
VERDICT_RE = re.compile(
    r"\b(?:vince|vincono|vincitore|vincitrice|vincente|vincenti|perdente|perdenti|sconfitt\w*|verdetto"
    r"|ha ragione|hanno ragione|ha torto|hanno torto|la voce migliore|la tesi migliore)\b")

# TASK-71: lettere di altri alfabeti identiche a lettere latine (omoglifi) e segni diacritici
# combinanti aggirerebbero le regex ASCII di §7.5–§7.7 («cоmprare» con la «о» cirillica, «VWСE»
# con la «С» cirillica, «cómprare» con l'accento combinante). Solo per questi controlli il testo
# è ripiegato su lettere latine senza segni diacritici (§7.4 resta sul testo NFKC).
_CONFUSABLES = str.maketrans({
    # cirillico
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
    "Т": "T", "У": "Y", "Х": "X", "Ѕ": "S", "І": "I", "Ј": "J", "Ԛ": "Q", "Ԝ": "W", "Ү": "Y",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "ѕ": "s", "і": "i",
    "ј": "j", "ԁ": "d", "ԛ": "q", "ԝ": "w", "һ": "h", "ӏ": "l", "ү": "y", "ɡ": "g",
    # greco
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N",
    "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "α": "a", "ι": "i", "κ": "k", "ν": "v",
    "ο": "o", "ρ": "p", "υ": "u",
    # armeno e latino esteso
    "օ": "o", "ս": "u", "ı": "i", "ȷ": "j",
})


def _fold(scan: str) -> str:
    """Omoglifi → lettere latine, poi via i segni diacritici (NFKD senza categoria Mn)."""
    decomposed = unicodedata.normalize("NFKD", scan.translate(_CONFUSABLES))
    return unicodedata.normalize("NFC", "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn"))


_WS_RE = re.compile(r"\s+")
_ITEM_REF_RE = re.compile(r"^[AR]-(IND|FAT|PRU)-[1-9]$")


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

def _count_codes(discarded: Iterable["Discard"]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in discarded:
        counts[item.code] = counts.get(item.code, 0) + 1
    return {code: counts[code] for code in sorted(counts)}


@dataclass(frozen=True)
class Discard:
    path: str  # "arguments[3]", "rebuttals[1]", "shared_points[0]", "contested_points[1]", "open_questions[1]"
    code: str


@dataclass(frozen=True)
class VerificationResult:
    admitted: list[dict[str, Any]]
    discarded: list[Discard]

    def by_code(self) -> dict[str, int]:
        return _count_codes(self.discarded)


@dataclass(frozen=True)
class SynthesisVerification:
    synthesis: dict[str, Any]
    discarded: list[Discard]

    def by_code(self) -> dict[str, int]:
        return _count_codes(self.discarded)

    @property
    def admitted_count(self) -> int:
        return (len(self.synthesis.get("shared_points", []))
                + len(self.synthesis.get("contested_points", []))
                + len(self.synthesis.get("open_questions", [])))


class _Reject(Exception):
    """Internal: carries the discard code of the item being checked."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """api-contracts §7.1: clean_text, collapse whitespace, strip."""
    return _WS_RE.sub(" ", clean_text(text, max_chars=10_000)).strip()


def _facts_by_id(case_file: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    facts: dict[str, Mapping[str, Any]] = {}
    for fact in case_file.get("facts") or []:
        if isinstance(fact, Mapping) and isinstance(fact.get("id"), str):
            facts[fact["id"]] = fact
    return facts


def _render(template: str, facts: Mapping[str, Mapping[str, Any]]) -> str:
    def repl(match: re.Match[str]) -> str:
        fact = facts.get("F" + match.group(1))
        if fact is None:
            return match.group(0)
        return str(fact.get("formatted"))

    return PLACEHOLDER_RE.sub(repl, template)


def render_template(template: str, case_file: Mapping[str, Any]) -> str:
    """Replace every valid ``{Fn}`` with ``facts[Fn].formatted`` (unknown ids are left as is)."""
    return _render(template, _facts_by_id(case_file))


# ---------------------------------------------------------------------------
# Context and single-text checks
# ---------------------------------------------------------------------------

class _Context:
    def __init__(self, case_file: Mapping[str, Any]) -> None:
        self.facts = _facts_by_id(case_file)
        symbols: set[str] = set()
        isins: set[str] = set()
        names: list[str] = []
        for inst in case_file.get("instruments") or []:
            if not isinstance(inst, Mapping):
                continue
            symbol = inst.get("symbol")
            if isinstance(symbol, str) and symbol:
                symbols.add(symbol)
            isin = inst.get("isin")
            if isinstance(isin, str) and isin:
                isins.add(isin)
            name = inst.get("name")
            if isinstance(name, str):
                names.append(_fold(name).lower())
        prefixes = {s.split(".", 1)[0] for s in symbols if "." in s}
        self.isins = frozenset(isins)
        self.tickers_ok = frozenset(symbols | prefixes | ALLOWED_ACRONYMS)
        self.names = tuple(names)
        # §7.4.1: instrument identifiers containing digits, longest first.
        ids_with_digits = sorted(
            {x for x in symbols | prefixes | isins if any(ch.isdigit() for ch in x)},
            key=lambda x: (-len(x), x),
        )
        self.id_res = tuple(re.compile(rf"(?<![\w.]){re.escape(x)}(?![\w])") for x in ids_with_digits)


def _scan_text(template: str) -> str:
    """Text for §7.4–§7.7: valid placeholders → space, then NFKC."""
    return unicodedata.normalize("NFKC", PLACEHOLDER_RE.sub(" ", template))


def _placeholder_ids(template: str) -> list[str]:
    return ["F" + m.group(1) for m in PLACEHOLDER_RE.finditer(template)]


def _check_instruments(scan: str, ctx: _Context) -> None:
    for m in ISIN_RE.finditer(scan):
        if m.group(0) not in ctx.isins:
            raise _Reject("strumento_non_ammesso")
    for m in TICKER_RE.finditer(scan):
        if m.group(0) not in ctx.tickers_ok:
            raise _Reject("strumento_non_ammesso")
    lower = scan.lower()
    for name, pattern in _ISSUER_RES:
        if pattern.search(lower) and not any(name in n for n in ctx.names):
            raise _Reject("strumento_non_ammesso")


def _has_free_figure(scan: str, fact_ids: list[str], ctx: _Context) -> bool:
    text = scan
    for pattern in ctx.id_res:
        text = pattern.sub(" ", text)
    allowed_years: set[str] = set()
    for fid in fact_ids:
        label = ctx.facts.get(fid, {}).get("label")
        if isinstance(label, str):
            allowed_years.update(m.group(0) for m in YEAR_RE.finditer(label))
    if allowed_years:
        text = YEAR_RE.sub(lambda m: " " if m.group(0) in allowed_years else m.group(0), text)
    for ch in text:
        if unicodedata.category(ch) in ("Nd", "Nl", "No"):
            return True
        if ch in FREE_SYMBOLS:
            return True
    for word in WORD_RE.findall(text.lower()):
        if word in QUANTITY_WORDS:
            return True
        if word not in ALLOWED_NUMERALS and NUMERAL_RE.fullmatch(word):
            return True
    return False


def _check_content(template: str, fact_ids: list[str], ctx: _Context) -> str | None:
    """Checks 11–14 on one normalized text; returns the first code or ``None``."""
    scan = _scan_text(template)
    folded = _fold(scan)
    try:
        _check_instruments(scan, ctx)
        if folded != scan:
            _check_instruments(folded, ctx)
    except _Reject as exc:
        return exc.code
    if _has_free_figure(scan, fact_ids, ctx):
        return "cifra_libera"
    lower = folded.lower()
    if OPERATIVE_RE.search(lower):
        return "indicazione_operativa"
    if VERDICT_RE.search(lower):
        return "verdetto"
    return None


# ---------------------------------------------------------------------------
# Parts: a text with its facts (argument, rebuttal, point, side, question)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Part:
    template: str
    fact_ids: list[str]   # deduplicated, original order
    max_chars: int
    question: bool = False

    @property
    def used(self) -> list[str]:
        out = list(self.fact_ids)
        for fid in _placeholder_ids(self.template):
            if fid not in out:
                out.append(fid)
        return out


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def _dedup(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def _text_or_reject(value: Any) -> str:
    if not isinstance(value, str):
        raise _Reject("schema_non_valido")
    template = normalize_text(value)
    if len(template) < MIN_TEXT_CHARS:
        raise _Reject("schema_non_valido")
    return template


def _fact_ids_or_reject(value: Any) -> list[str]:
    if not _is_str_list(value):
        raise _Reject("schema_non_valido")
    return _dedup(value)


def _check_parts(parts: list[_Part], ctx: _Context,
                 extraneous: Callable[[], bool] | None = None) -> None:
    """Checks 3–14 in precedence order; each check runs on every part before the next check."""
    countable = [p for p in parts if not p.question]
    # 3, 4
    if any(not p.fact_ids for p in countable):
        raise _Reject("nessun_fatto")
    if any(len(p.fact_ids) > MAX_FACTS_PER_ITEM for p in countable):
        raise _Reject("troppi_fatti")
    # 5, 6
    if any(fid not in ctx.facts for p in parts for fid in p.used):
        raise _Reject("fatto_inesistente")
    if any(ctx.facts[fid].get("citable") is not True for p in parts for fid in p.used):
        raise _Reject("fatto_non_citabile")
    # 7
    if any("{" in s or "}" in s for s in (PLACEHOLDER_RE.sub("", p.template) for p in parts)):
        raise _Reject("segnaposto_malformato")
    # 8
    for p in parts:
        ids = _placeholder_ids(p.template)
        if p.question and ids:
            raise _Reject("segnaposto_non_citato")
        if any(fid not in p.fact_ids for fid in ids):
            raise _Reject("segnaposto_non_citato")
    # 9
    if extraneous is not None and extraneous():
        raise _Reject("fatto_estraneo")
    # 10
    if any(len(p.template) > p.max_chars for p in parts):
        raise _Reject("testo_troppo_lungo")
    # 11–14: code by code across parts
    codes = [_check_content(p.template, p.fact_ids, ctx) for p in parts]
    for code in ("strumento_non_ammesso", "cifra_libera", "indicazione_operativa", "verdetto"):
        if code in codes:
            raise _Reject(code)


def _voice_code(voice_id: str) -> str:
    try:
        return VOICE_CODES[voice_id]
    except KeyError:
        raise ValueError(f"unknown voice: {voice_id!r}") from None


def _raw_list(raw: Mapping[str, Any], key: str) -> list[Any]:
    value = raw.get(key) if isinstance(raw, Mapping) else None
    return value if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# Opening
# ---------------------------------------------------------------------------

def verify_opening(voice_id: str, raw: Mapping[str, Any],
                   case_file: Mapping[str, Any]) -> VerificationResult:
    code = _voice_code(voice_id)
    ctx = _Context(case_file)
    admitted: list[dict[str, Any]] = []
    discarded: list[Discard] = []
    for index, item in enumerate(_raw_list(raw, "arguments")):
        path = f"arguments[{index}]"
        try:
            if not isinstance(item, Mapping):
                raise _Reject("schema_non_valido")
            theme, stance = item.get("theme"), item.get("stance")
            if not isinstance(theme, str) or theme not in THEMES:
                raise _Reject("schema_non_valido")
            if not isinstance(stance, str) or stance not in ARGUMENT_STANCES:
                raise _Reject("schema_non_valido")
            template = _text_or_reject(item.get("text"))
            fact_ids = _fact_ids_or_reject(item.get("fact_ids"))
            _check_parts([_Part(template, fact_ids, MAX_ARGUMENT_CHARS)], ctx)
            if len(admitted) >= MAX_ARGUMENTS_PER_VOICE:
                raise _Reject("troppi_argomenti")
        except _Reject as exc:
            discarded.append(Discard(path, exc.code))
            continue
        admitted.append({
            "id": f"A-{code}-{len(admitted) + 1}",
            "voice": voice_id,
            "phase": "apertura",
            "theme": theme,
            "stance": stance,
            "text": _render(template, ctx.facts),
            "text_template": template,
            "fact_ids": fact_ids,
        })
    return VerificationResult(admitted=admitted, discarded=discarded)


# ---------------------------------------------------------------------------
# Rebuttals
# ---------------------------------------------------------------------------

def verify_rebuttals(voice_id: str, raw: Mapping[str, Any], case_file: Mapping[str, Any],
                     arguments: list[dict[str, Any]]) -> VerificationResult:
    """``arguments``: all admitted opening arguments (same-voice ones are excluded here)."""
    code = _voice_code(voice_id)
    ctx = _Context(case_file)
    targets: dict[str, str] = {}
    for arg in arguments or []:
        if isinstance(arg, Mapping) and isinstance(arg.get("id"), str):
            targets[arg["id"]] = arg.get("voice")
    admitted: list[dict[str, Any]] = []
    discarded: list[Discard] = []
    for index, item in enumerate(_raw_list(raw, "rebuttals")):
        path = f"rebuttals[{index}]"
        try:
            if not isinstance(item, Mapping):
                raise _Reject("schema_non_valido")
            target, stance = item.get("target_argument_id"), item.get("stance")
            if not isinstance(target, str):
                raise _Reject("schema_non_valido")
            if not isinstance(stance, str) or stance not in REBUTTAL_STANCES:
                raise _Reject("schema_non_valido")
            template = _text_or_reject(item.get("text"))
            fact_ids = _fact_ids_or_reject(item.get("fact_ids"))
            target_voice = targets.get(target)
            if not target.startswith("A-") or target_voice is None or target_voice == voice_id:
                raise _Reject("riferimento_non_ammesso")
            _check_parts([_Part(template, fact_ids, MAX_REBUTTAL_CHARS)], ctx)
            if len(admitted) >= MAX_REBUTTALS_PER_VOICE:
                raise _Reject("troppi_argomenti")
        except _Reject as exc:
            discarded.append(Discard(path, exc.code))
            continue
        admitted.append({
            "id": f"R-{code}-{len(admitted) + 1}",
            "voice": voice_id,
            "phase": "replica",
            "target_argument_id": target,
            "target_voice": target_voice,
            "stance": stance,
            "text": _render(template, ctx.facts),
            "text_template": template,
            "fact_ids": fact_ids,
        })
    return VerificationResult(admitted=admitted, discarded=discarded)


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def _voices_of(ids: list[str], refs: Mapping[str, Mapping[str, Any]]) -> list[str]:
    present = {refs[i].get("voice") for i in ids}
    return [v for v in VOICE_ORDER if v in present]


def _metric_codes(fact_ids: Iterable[str], ctx: _Context) -> list[str]:
    out: list[str] = []
    for fid in fact_ids:
        key = ctx.facts.get(fid, {}).get("key")
        if isinstance(key, str) and key.startswith("metric."):
            metric = key[len("metric."):]
            if metric not in out:
                out.append(metric)
    return out


def verify_synthesis(raw: Mapping[str, Any], case_file: Mapping[str, Any],
                     arguments: list[dict[str, Any]],
                     rebuttals: list[dict[str, Any]]) -> SynthesisVerification:
    ctx = _Context(case_file)
    refs: dict[str, Mapping[str, Any]] = {}
    for item in list(arguments or []) + list(rebuttals or []):
        if isinstance(item, Mapping) and isinstance(item.get("id"), str) \
                and _ITEM_REF_RE.match(item["id"]):
            refs[item["id"]] = item

    def ref_facts(ids: Iterable[str]) -> set[str]:
        out: set[str] = set()
        for i in ids:
            fids = refs[i].get("fact_ids")
            if isinstance(fids, list):
                out.update(f for f in fids if isinstance(f, str))
        return out

    discarded: list[Discard] = []

    # Shared points
    shared: list[dict[str, Any]] = []
    for index, item in enumerate(_raw_list(raw, "shared_points")):
        path = f"shared_points[{index}]"
        try:
            if not isinstance(item, Mapping):
                raise _Reject("schema_non_valido")
            template = _text_or_reject(item.get("text"))
            fact_ids = _fact_ids_or_reject(item.get("fact_ids"))
            if not _is_str_list(item.get("argument_ids")):
                raise _Reject("schema_non_valido")
            arg_ids = _dedup(item["argument_ids"])
            if any(i not in refs for i in arg_ids):
                raise _Reject("riferimento_non_ammesso")
            voices = _voices_of(arg_ids, refs)
            if len(voices) < 2:
                raise _Reject("riferimento_non_ammesso")
            part = _Part(template, fact_ids, MAX_POINT_CHARS)
            _check_parts([part], ctx,
                         extraneous=lambda: not set(part.used) <= ref_facts(arg_ids))
            if len(shared) >= MAX_SHARED_POINTS:
                raise _Reject("troppi_argomenti")
        except _Reject as exc:
            discarded.append(Discard(path, exc.code))
            continue
        shared.append({
            "id": f"S{len(shared) + 1}",
            "text": _render(template, ctx.facts),
            "text_template": template,
            "fact_ids": fact_ids,
            "argument_ids": arg_ids,
            "voices": voices,
        })

    # Contested points
    contested: list[dict[str, Any]] = []
    for index, item in enumerate(_raw_list(raw, "contested_points")):
        path = f"contested_points[{index}]"
        try:
            if not isinstance(item, Mapping):
                raise _Reject("schema_non_valido")
            template = _text_or_reject(item.get("text"))
            fact_ids = _fact_ids_or_reject(item.get("fact_ids"))
            raw_sides = item.get("sides")
            if not isinstance(raw_sides, list) or len(raw_sides) != 2:
                raise _Reject("schema_non_valido")
            sides_in: list[tuple[str, list[str], list[str]]] = []
            for side in raw_sides:
                if not isinstance(side, Mapping) or not _is_str_list(side.get("argument_ids")):
                    raise _Reject("schema_non_valido")
                summary = _text_or_reject(side.get("summary"))
                side_facts = _fact_ids_or_reject(side.get("fact_ids"))
                sides_in.append((summary, side_facts, _dedup(side["argument_ids"])))
            side_voices: list[list[str]] = []
            for _summary, _facts, arg_ids in sides_in:
                if not arg_ids or any(i not in refs for i in arg_ids):
                    raise _Reject("riferimento_non_ammesso")
                side_voices.append(_voices_of(arg_ids, refs))
            if set(side_voices[0]) & set(side_voices[1]):
                raise _Reject("riferimento_non_ammesso")
            point_part = _Part(template, fact_ids, MAX_POINT_CHARS)
            side_parts = [_Part(s, f, MAX_SIDE_CHARS) for s, f, _a in sides_in]
            all_refs = [i for _s, _f, ids in sides_in for i in ids]
            parts = [point_part, *side_parts]
            _check_parts(parts, ctx, extraneous=lambda: not {
                fid for p in parts for fid in p.used} <= ref_facts(all_refs))
            if len(contested) >= MAX_CONTESTED_POINTS:
                raise _Reject("troppi_argomenti")
        except _Reject as exc:
            discarded.append(Discard(path, exc.code))
            continue
        contested.append({
            "id": f"C{len(contested) + 1}",
            "text": _render(template, ctx.facts),
            "text_template": template,
            "fact_ids": fact_ids,
            "metric_codes": _metric_codes(
                [*fact_ids, *(f for _s, fs, _a in sides_in for f in fs)], ctx),
            "sides": [
                {
                    "voices": voices,
                    "argument_ids": arg_ids,
                    "summary": _render(summary, ctx.facts),
                    "summary_template": summary,
                    "fact_ids": side_facts,
                }
                for (summary, side_facts, arg_ids), voices in zip(sides_in, side_voices)
            ],
        })

    # Open questions
    questions: list[dict[str, Any]] = []
    for index, item in enumerate(_raw_list(raw, "open_questions")):
        path = f"open_questions[{index}]"
        try:
            if not isinstance(item, Mapping):
                raise _Reject("schema_non_valido")
            template = _text_or_reject(item.get("text"))
            _check_parts([_Part(template, [], MAX_QUESTION_CHARS, question=True)], ctx)
            if len(questions) >= MAX_OPEN_QUESTIONS:
                raise _Reject("troppi_argomenti")
        except _Reject as exc:
            discarded.append(Discard(path, exc.code))
            continue
        questions.append({"id": f"Q{len(questions) + 1}", "text": template})

    return SynthesisVerification(
        synthesis={"shared_points": shared, "contested_points": contested,
                   "open_questions": questions},
        discarded=discarded,
    )
