"""Metric registry of Doctor policies (contract §2) and their computation.

Every metric is in percentage points (0-100) over the *invested value*: the
market value of the non-cash holdings of the snapshot (the cash balance and
cash positions are excluded, D02). Values are never rounded here; the
evaluator compares unrounded values and the UI rounds with the rule
precision.

The computations reuse the shared deterministic services:
- asset class: ``holding_asset_class`` (shared classifier, TASK-35);
- concentration: canonical security = ISIN (fallback asset_id), so the same
  security listed on two exchanges or held in two portfolios is one;
- USA: the same sources as ``compute_geographic_exposure`` (justETF country
  weights, else ``infer_region_profile``) with the unclassified share made
  explicit, giving conservative bounds;
- TER: ``resolve_holding_ters`` with the covered share declared;
- overlap: ``compute_overlap_score`` on the fund holdings.

Unavailable data is never turned into 0: value ``None`` and quality
``missing``. See docs/doctor2/financial-methodology.md.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..asset_classification import BOND, COMMODITY, EQUITY, GOLD, UNKNOWN
from ..portfolio_doctor._health import (
    _country_to_region,
    compute_overlap_score,
    infer_region_profile,
    resolve_holding_ters,
)
from ..portfolio_doctor._holdings import AnalyzedHolding, holding_asset_class, holding_classification
from .snapshot import DoctorSnapshot

METHODOLOGY_VERSION = "doctor-policy-1.0"
MAX_CONTRIBUTORS = 10
INVESTED_DENOMINATOR = "Valore investito escluso cash (saldo di cassa e posizioni di tipo cash)"


@dataclass(frozen=True)
class MetricDefinition:
    code: str
    label: str
    # Short subject used in reasons ("Non possiamo verificare il limite USA").
    short_label: str
    operators: tuple[str, ...]
    denominator: str
    description: str
    source: str
    unit: str = "pct"
    default_warning_margin: float = 2.0
    default_precision: int = 1

    def to_read(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "unit": self.unit,
            "operators": list(self.operators),
            "denominator": self.denominator,
            "description": self.description,
            "source": self.source,
            "default_warning_margin": self.default_warning_margin,
            "methodology_version": METHODOLOGY_VERSION,
        }


@dataclass
class MetricValue:
    code: str
    value: float | None
    lower: float | None
    upper: float | None
    coverage_pct: float | None
    quality: str  # ok | partial | stale | missing
    source: str
    denominator: str
    denominator_value: float | None
    unit: str = "pct"
    contributors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # PRD §6 metadata: oldest quote used (ISO), computation time (ISO UTC),
    # methodology. Filled by ``compute_metrics``.
    quote_as_of: str | None = None
    calculated_at: str | None = None
    methodology_version: str = METHODOLOGY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_MIN_MAX_RANGE = ("min", "max", "range")

METRIC_REGISTRY: dict[str, MetricDefinition] = {
    d.code: d
    for d in (
        MetricDefinition(
            code="equity_weight_pct",
            label="Quota azionaria",
            short_label="sulla quota azionaria",
            operators=_MIN_MAX_RANGE,
            denominator=INVESTED_DENOMINATOR,
            description="Peso delle posizioni classificate come azionarie dal classificatore comune.",
            source="asset_classification",
        ),
        MetricDefinition(
            code="bond_weight_pct",
            label="Quota obbligazionaria",
            short_label="sulla quota obbligazionaria",
            operators=_MIN_MAX_RANGE,
            denominator=INVESTED_DENOMINATOR,
            description="Peso delle posizioni classificate come obbligazionarie dal classificatore comune.",
            source="asset_classification",
        ),
        MetricDefinition(
            code="gold_weight_pct",
            label="Quota oro / metalli preziosi",
            short_label="sulla quota oro",
            operators=_MIN_MAX_RANGE,
            denominator=INVESTED_DENOMINATOR,
            description=(
                "Peso delle posizioni in oro (classe gold) e in metalli preziosi (classe commodity "
                "con argento/platino/palladio/precious metals nella descrizione)."
            ),
            source="asset_classification",
        ),
        MetricDefinition(
            code="max_single_position_pct",
            label="Peso massimo singola posizione",
            short_label="sulla singola posizione",
            operators=("max",),
            denominator=INVESTED_DENOMINATOR,
            description=(
                "Peso della posizione più grande, per strumento canonico (ISIN, altrimenti asset): "
                "lo stesso titolo su più borse o in più portafogli conta una volta."
            ),
            source="canonical_security",
        ),
        MetricDefinition(
            code="top3_positions_pct",
            label="Peso prime tre posizioni",
            short_label="sulle prime tre posizioni",
            operators=("max",),
            denominator=INVESTED_DENOMINATOR,
            description="Somma dei pesi delle tre posizioni più grandi (strumento canonico).",
            source="canonical_security",
        ),
        MetricDefinition(
            code="usa_exposure_pct",
            label="Esposizione USA (look-through)",
            short_label="USA",
            operators=("max", "min", "range"),
            denominator=INVESTED_DENOMINATOR,
            description=(
                "Quota del valore investito esposta agli Stati Uniti, per paese dei sottostanti "
                "(pesi paese justETF, altrimenti inferenza dall'indice). La quota non classificata "
                "è esplicita e produce un intervallo prudenziale."
            ),
            source="geographic_lookthrough",
        ),
        MetricDefinition(
            code="weighted_ter_pct",
            label="TER medio ponderato",
            short_label="sul TER",
            operators=("max",),
            denominator="Valore investito con TER noto (universo coperto)",
            description="Costo annuo (TER) medio ponderato per valore sulle posizioni con TER noto.",
            source="ter_registry",
            default_warning_margin=0.05,
            default_precision=2,
        ),
        MetricDefinition(
            code="etf_overlap_pct",
            label="Overlap ETF",
            short_label="sull'overlap ETF",
            operators=("max",),
            denominator="Coppie di fondi/ETF, pesate per il prodotto dei pesi",
            description=(
                "Sovrapposizione stimata fra i fondi/ETF del portafoglio (euristica del Doctor); "
                "misura diversa dalla concentrazione per singola posizione."
            ),
            source="overlap_heuristic",
            default_warning_margin=5.0,
        ),
    )
}

METRIC_CODES: tuple[str, ...] = tuple(METRIC_REGISTRY)

# Precious metals other than gold (classe commodity del classificatore comune).
_PRECIOUS_METALS = re.compile(
    r"precious metals?|metalli preziosi|\bsilver\b|\bargento\b|\bplatinum\b|\bplatino\b|"
    r"\bpalladium\b|\bpalladio\b",
    re.IGNORECASE,
)


def format_it(value: float, decimals: int) -> str:
    """Italian decimal comma, fixed decimals (``46,6``)."""
    text = f"{value:.{max(0, int(decimals))}f}"
    if text.startswith("-") and float(text) == 0:
        text = text[1:]
    return text.replace(".", ",")


def format_threshold_it(value: float) -> str:
    """Threshold without useless zeros (``35``, ``0,25``)."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def policy_asset_class(holding: AnalyzedHolding, asset_class: str | None = None) -> str:
    """Asset class used by the policy metrics.

    The shared classifier's class, except that a ``commodity`` product on
    precious metals (silver, platinum, palladium, a precious-metals basket)
    counts with gold (``gold_weight_pct`` = gold + precious metals). Miners are
    equity already (classifier override).
    """
    if asset_class is None:
        asset_class = holding_asset_class(holding)
    if asset_class == COMMODITY:
        text = " ".join(
            part for part in (
                holding.name, holding.enrichment_name, holding.investment_focus,
                holding.index_tracked, holding.category,
            ) if part
        )
        if _PRECIOUS_METALS.search(text):
            return GOLD
    return asset_class


def classification_key(holding: AnalyzedHolding) -> tuple:
    """asset_id/ISIN plus every input of the shared classifier (not the value)."""
    return (
        holding.asset_id, holding.isin, holding.symbol, holding.name, holding.asset_type,
        holding.quote_currency, holding.investment_focus, holding.index_tracked, holding.category,
        holding.enrichment_name,
    )


class ClassificationMemo:
    """Per-computation memo of the per-holding classification work.

    The shared functions (``classify_asset``, ``infer_region_profile``,
    ``resolve_holding_ters``) are unchanged and still do the work; this only
    avoids repeating it for the same holding inside one computation. Keys are
    ``classification_key`` (plus the enrichment fields that the region
    inference reads), never the market value, so the results are identical to
    calling the shared functions directly. Never global: ``compute_metrics``
    creates one per call unless the caller passes one (the Scenario Lab shares
    it between the before/after of one preview; the repository data it reads
    is the same within that request). ``enabled=False`` disables it (tests).
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._classification: dict[tuple, Any] = {}
        self._policy_class: dict[tuple, str] = {}
        self._region: dict[tuple, dict[str, float]] = {}
        self._ter: dict[tuple, tuple[float | None, str]] = {}

    def classification(self, holding: AnalyzedHolding) -> Any:
        if not self.enabled:
            return holding_classification(holding)
        key = classification_key(holding)
        if key not in self._classification:
            self._classification[key] = holding_classification(holding)
        return self._classification[key]

    def policy_asset_class(self, holding: AnalyzedHolding) -> str:
        if not self.enabled:
            return policy_asset_class(holding)
        key = classification_key(holding)
        if key not in self._policy_class:
            self._policy_class[key] = policy_asset_class(holding, self.classification(holding).asset_class)
        return self._policy_class[key]

    def region_profile(self, holding: AnalyzedHolding, enrich: dict | None) -> dict[str, float]:
        if not self.enabled:
            return infer_region_profile(holding, enrich=enrich)
        extra = (
            (str(enrich.get("investment_focus") or ""), str(enrich.get("index_tracked") or ""),
             str(enrich.get("description") or ""))
            if isinstance(enrich, dict) else None
        )
        key = (classification_key(holding), extra)
        if key not in self._region:
            self._region[key] = infer_region_profile(holding, enrich=enrich)
        return dict(self._region[key])

    def ters(self, holdings: list[AnalyzedHolding], repo: Any) -> dict[int, tuple[float | None, str]]:
        if not self.enabled:
            return resolve_holding_ters(holdings, repo)
        todo = [h for h in holdings if classification_key(h) not in self._ter]
        if todo:
            resolved = resolve_holding_ters(todo, repo)
            for h in todo:
                self._ter[classification_key(h)] = resolved.get(h.asset_id, (None, "none"))
        return {h.asset_id: self._ter[classification_key(h)] for h in holdings}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _contributor(holding: AnalyzedHolding, weight: float) -> dict[str, Any]:
    return {"symbol": holding.symbol, "name": holding.name, "isin": holding.isin, "weight_pct": weight}


def _top(contributors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(contributors, key=lambda c: (-c["weight_pct"], str(c.get("symbol") or "")))[:MAX_CONTRIBUTORS]


def canonical_key(holding: AnalyzedHolding) -> str:
    isin = (holding.isin or "").strip().upper()
    return f"isin:{isin}" if isin else f"asset:{holding.asset_id}"


def canonical_securities(snapshot: DoctorSnapshot) -> list[dict[str, Any]]:
    """Invested holdings grouped by canonical security, heaviest first.

    Each item: key, symbol, name, isin, weight_pct (unrounded), market_value,
    holdings (the merged AnalyzedHolding list).
    """
    groups: dict[str, dict[str, Any]] = {}
    for h in snapshot.invested_holdings:
        key = canonical_key(h)
        group = groups.get(key)
        if group is None:
            group = groups[key] = {
                "key": key, "symbol": h.symbol, "name": h.name, "isin": h.isin,
                "weight_pct": 0.0, "market_value": 0.0, "holdings": [],
            }
        group["weight_pct"] += snapshot.weight_of(h)
        group["market_value"] += max(0.0, float(h.market_value))
        group["holdings"].append(h)
    return sorted(groups.values(), key=lambda g: (-g["market_value"], g["key"]))


def _merged_holding(group: dict[str, Any]) -> AnalyzedHolding:
    first: AnalyzedHolding = group["holdings"][0]
    merged = AnalyzedHolding(**first.__dict__)
    merged.market_value = group["market_value"]
    merged.weight_pct = group["weight_pct"]
    return merged


def _missing(code: str, source: str, denominator: str, denominator_value: float | None, note: str) -> MetricValue:
    return MetricValue(
        code=code, value=None, lower=None, upper=None, coverage_pct=None, quality="missing",
        source=source, denominator=denominator, denominator_value=denominator_value, notes=[note],
    )


def _bounded(
    code: str, *, known: float, unclassified: float, source: str, denominator_value: float,
    contributors: list[dict[str, Any]], notes: list[str],
) -> MetricValue:
    """Value with conservative bounds from an explicit unclassified share.

    lower = known share, upper = known + unclassified, coverage = 100 -
    unclassified; the point value is the known share rescaled to the
    classified part (``known / coverage``), equal to the bounds at full
    coverage.
    """
    unclassified = min(100.0, max(0.0, unclassified))
    coverage = 100.0 - unclassified
    if coverage <= 1e-9:
        return MetricValue(
            code=code, value=None, lower=0.0, upper=100.0, coverage_pct=0.0, quality="missing",
            source=source, denominator=INVESTED_DENOMINATOR, denominator_value=denominator_value,
            contributors=_top(contributors),
            notes=notes + ["Nessuna posizione classificata: valore non disponibile."],
        )
    if unclassified <= 1e-9:
        return MetricValue(
            code=code, value=known, lower=known, upper=known, coverage_pct=100.0, quality="ok",
            source=source, denominator=INVESTED_DENOMINATOR, denominator_value=denominator_value,
            contributors=_top(contributors), notes=notes,
        )
    return MetricValue(
        code=code, value=known / coverage * 100.0, lower=known, upper=min(100.0, known + unclassified),
        coverage_pct=coverage, quality="partial", source=source, denominator=INVESTED_DENOMINATOR,
        denominator_value=denominator_value, contributors=_top(contributors),
        notes=notes + [f"Quota non classificata: {format_it(unclassified, 1)}% del valore investito."],
    )


# ---------------------------------------------------------------------------
# metric computations
# ---------------------------------------------------------------------------


def _asset_class_metrics(snapshot: DoctorSnapshot, memo: ClassificationMemo) -> dict[str, MetricValue]:
    known: dict[str, float] = defaultdict(float)
    contributors: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unknown_contributors: list[dict[str, Any]] = []
    for h in snapshot.invested_holdings:
        weight = snapshot.weight_of(h)
        asset_class = memo.policy_asset_class(h)
        if asset_class == UNKNOWN:
            unknown_contributors.append(_contributor(h, weight))
            continue
        known[asset_class] += weight
        contributors[asset_class].append(_contributor(h, weight))
    unclassified = sum(c["weight_pct"] for c in unknown_contributors)
    notes = []
    if unknown_contributors:
        names = ", ".join(c["symbol"] for c in _top(unknown_contributors))
        notes.append(f"Asset class non riconosciuta per: {names}.")
    out = {}
    for code, asset_class in (
        ("equity_weight_pct", EQUITY), ("bond_weight_pct", BOND), ("gold_weight_pct", GOLD),
    ):
        out[code] = _bounded(
            code, known=known[asset_class], unclassified=unclassified, source="asset_classification",
            denominator_value=snapshot.invested_value, contributors=contributors[asset_class],
            notes=list(notes),
        )
    return out


def _concentration_metrics(snapshot: DoctorSnapshot, groups: list[dict[str, Any]]) -> dict[str, MetricValue]:
    contributors = [
        {"symbol": g["symbol"], "name": g["name"], "isin": g["isin"], "weight_pct": g["weight_pct"]}
        for g in groups
    ]
    notes = []
    multi = [g for g in groups if len(g["holdings"]) > 1]
    if multi:
        notes.append(
            "Stesso strumento (ISIN) su più listing aggregato: "
            + ", ".join("/".join(h.symbol for h in g["holdings"]) for g in multi) + "."
        )
    base = {
        "lower": None, "upper": None, "coverage_pct": 100.0, "quality": "ok",
        "source": "canonical_security", "denominator": INVESTED_DENOMINATOR,
        "denominator_value": snapshot.invested_value,
    }
    max_single = groups[0]["weight_pct"] if groups else None
    top3 = sum(g["weight_pct"] for g in groups[:3]) if groups else None
    return {
        "max_single_position_pct": MetricValue(
            code="max_single_position_pct", value=max_single, **{**base, "lower": max_single, "upper": max_single},
            contributors=contributors[:MAX_CONTRIBUTORS], notes=list(notes),
        ),
        "top3_positions_pct": MetricValue(
            code="top3_positions_pct", value=top3, **{**base, "lower": top3, "upper": top3},
            contributors=contributors[:3], notes=list(notes),
        ),
    }


def _enrichment_map(snapshot: DoctorSnapshot, repo: Any) -> dict[int, dict]:
    if repo is None:
        return {}
    try:
        loaded = repo.get_etf_enrichment_bulk([h.asset_id for h in snapshot.invested_holdings])
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def holding_usa_split(
    holding: AnalyzedHolding, enrich: dict | None, memo: ClassificationMemo | None = None,
) -> tuple[float, float, str]:
    """(USA %, classified %, source) of one holding, 0-100 of its own value.

    Same sources as ``compute_geographic_exposure``: justETF country weights
    when stored, else ``infer_region_profile``. What no source attributes to a
    country is unclassified (an ETF with an unrecognized index, country
    weights that do not reach 100).
    """
    country_weights = enrich.get("country_weights") if isinstance(enrich, dict) else None
    if country_weights:
        usa = 0.0
        total = 0.0
        for cw in country_weights:
            try:
                pct = max(0.0, float(cw.get("percentage") or 0.0))
            except (TypeError, ValueError, AttributeError):
                continue
            total += pct
            if _country_to_region(str(cw.get("name") or "")) == "usa":
                usa += pct
        classified = min(100.0, total)
        return min(usa, classified), classified, "etf_country_weights"
    profile = memo.region_profile(holding, enrich) if memo is not None else infer_region_profile(holding, enrich=enrich)
    if not profile:
        return 0.0, 0.0, "none"
    classified = min(100.0, sum(max(0.0, v) for v in profile.values()))
    return min(max(0.0, profile.get("usa", 0.0)), classified), classified, "region_inference"


def _usa_metric(
    snapshot: DoctorSnapshot, enrichment: dict[int, dict], has_repo: bool, memo: ClassificationMemo,
) -> MetricValue:
    known = 0.0
    unclassified = 0.0
    contributors = []
    unclassified_symbols = []
    inferred_share = 0.0
    for h in snapshot.invested_holdings:
        weight = snapshot.weight_of(h)
        usa, classified, source = holding_usa_split(h, enrichment.get(h.asset_id), memo)
        known += weight * usa / 100.0
        unclassified += weight * (100.0 - classified) / 100.0
        if source == "region_inference":
            inferred_share += weight
        if usa > 0:
            contributors.append(_contributor(h, weight * usa / 100.0))
        if classified < 100.0:
            unclassified_symbols.append(h.symbol)
    notes = []
    if inferred_share > 0:
        notes.append(
            "Per una parte del valore la ripartizione geografica è stimata dall'indice/valuta "
            "(nessun peso paese salvato)."
        )
    if unclassified_symbols:
        notes.append("Paese dei sottostanti non disponibile per: " + ", ".join(sorted(set(unclassified_symbols))[:10]) + ".")
    if not has_repo:
        notes.append("Calcolo senza dati di arricchimento ETF: solo inferenza deterministica.")
    return _bounded(
        "usa_exposure_pct", known=known, unclassified=unclassified,
        source="geographic_lookthrough" if has_repo else "region_inference",
        denominator_value=snapshot.invested_value, contributors=contributors, notes=notes,
    )


def _ter_metric(snapshot: DoctorSnapshot, repo: Any, memo: ClassificationMemo) -> MetricValue:
    holdings = snapshot.invested_holdings
    resolved = memo.ters(holdings, repo)
    covered = 0.0
    cost = 0.0
    inferred = 0.0
    contributors = []
    uncovered_symbols = []
    for h in holdings:
        weight = snapshot.weight_of(h)
        ter, source = resolved.get(h.asset_id, (None, "none"))
        if ter is None:
            uncovered_symbols.append(h.symbol)
            continue
        covered += weight
        cost += weight * float(ter)
        if source == "inferred":
            inferred += weight
        contributors.append(_contributor(h, weight * float(ter) / 100.0))
    source = "ter_registry" if repo is not None else "ter_inferred"
    denominator = METRIC_REGISTRY["weighted_ter_pct"].denominator
    if covered <= 1e-9:
        return _missing(
            "weighted_ter_pct", source, denominator, 0.0,
            "TER non disponibile per nessuna posizione.",
        )
    notes = []
    if inferred > 0:
        notes.append(f"TER stimato da regole deterministiche per il {format_it(inferred, 1)}% del valore investito.")
    if uncovered_symbols:
        notes.append("TER non disponibile per: " + ", ".join(sorted(set(uncovered_symbols))[:10]) + ".")
    value = cost / covered
    full = covered >= 100.0 - 1e-9
    # Contributors: weight_pct = contribution of the holding to the TER over
    # the invested value (pp of TER), heaviest first.
    return MetricValue(
        code="weighted_ter_pct",
        value=value,
        # Uncovered TER >= 0: the TER over the whole invested value is at least
        # the covered cost spread over 100%; no upper bound is known.
        lower=value if full else cost / 100.0,
        upper=value if full else None,
        coverage_pct=100.0 if full else covered,
        quality="ok" if full else "partial",
        source=source,
        denominator=denominator,
        denominator_value=snapshot.invested_value * covered / 100.0,
        contributors=_top(contributors),
        notes=notes,
    )


def is_fund_holding(holding: AnalyzedHolding, memo: ClassificationMemo | None = None) -> bool:
    if (holding.asset_type or "").lower() in {"etf", "fund"}:
        return True
    classification = memo.classification(holding) if memo is not None else holding_classification(holding)
    return classification.is_exchange_traded_product


def _overlap_metric(
    snapshot: DoctorSnapshot, memo: ClassificationMemo, groups: list[dict[str, Any]],
) -> MetricValue:
    funds = [_merged_holding(g) for g in groups if is_fund_holding(g["holdings"][0], memo)]
    fund_value = sum(f.market_value for f in funds)
    notes = ["Misura euristica della sovrapposizione fra fondi (arrotondata a 0,1); distinta dalla concentrazione."]
    if len(funds) < 2:
        value = 0.0
        notes.append("Meno di due fondi/ETF: nessuna coppia da confrontare.")
    else:
        value = compute_overlap_score(funds)
    return MetricValue(
        code="etf_overlap_pct", value=value, lower=value, upper=value, coverage_pct=100.0, quality="ok",
        source="overlap_heuristic", denominator=METRIC_REGISTRY["etf_overlap_pct"].denominator,
        denominator_value=fund_value,
        contributors=_top([_contributor(f, snapshot.weight_of(f)) for f in funds]),
        notes=notes,
    )


def compute_metrics(
    snapshot: DoctorSnapshot, repo: Any = None, *, now: datetime | None = None,
    memo: ClassificationMemo | None = None,
) -> dict[str, MetricValue]:
    """All registry metrics of a snapshot, computed once.

    ``repo`` is optional: with it TER and country weights come from the stored
    enrichment/metadata; without it (tests, Scenario Lab on simulated
    holdings) only the deterministic fallbacks are used (``infer_ter``,
    ``infer_region_profile``) and the source says so. Every metric carries
    ``quote_as_of`` (oldest quote of the snapshot), ``calculated_at`` (``now``,
    default the current UTC time) and ``methodology_version``.
    """
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    stamp = {"quote_as_of": snapshot.quote_as_of, "calculated_at": current.isoformat()}
    if snapshot.is_empty:
        return {
            code: _stamped(_missing(code, d.source, d.denominator, 0.0, "Nessuna posizione investita."), stamp)
            for code, d in METRIC_REGISTRY.items()
        }
    memo = memo if memo is not None else ClassificationMemo()
    enrichment = _enrichment_map(snapshot, repo)
    groups = canonical_securities(snapshot)  # once per call (concentration + overlap)
    metrics: dict[str, MetricValue] = {}
    metrics.update(_asset_class_metrics(snapshot, memo))
    metrics.update(_concentration_metrics(snapshot, groups))
    metrics["usa_exposure_pct"] = _usa_metric(snapshot, enrichment, repo is not None, memo)
    metrics["weighted_ter_pct"] = _ter_metric(snapshot, repo, memo)
    metrics["etf_overlap_pct"] = _overlap_metric(snapshot, memo, groups)

    if snapshot.stale_symbols or snapshot.sync_failed:
        note = "Quotazioni non aggiornate: " + (", ".join(snapshot.stale_symbols) or "sincronizzazione fallita") + "."
        for metric in metrics.values():
            if metric.quality != "missing":
                metric.quality = "stale"
            metric.notes.append(note)
    return {code: _stamped(metrics[code], stamp) for code in METRIC_CODES}


def _stamped(metric: MetricValue, stamp: dict[str, Any]) -> MetricValue:
    metric.quote_as_of = stamp["quote_as_of"]
    metric.calculated_at = stamp["calculated_at"]
    metric.methodology_version = METHODOLOGY_VERSION
    return metric


def metric_definitions() -> list[dict[str, Any]]:
    return [d.to_read() for d in METRIC_REGISTRY.values()]
