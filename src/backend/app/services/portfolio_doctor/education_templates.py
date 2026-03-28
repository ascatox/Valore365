from __future__ import annotations

from typing import Callable

from ...schemas.portfolio_doctor import (
    PortfolioHealthAlert,
    PortfolioHealthEducation,
    PortfolioHealthMetrics,
)


def build_alert_education(
    alert: PortfolioHealthAlert,
    metrics: PortfolioHealthMetrics,
) -> PortfolioHealthEducation | None:
    builders: dict[str, Callable[[PortfolioHealthAlert, PortfolioHealthMetrics], PortfolioHealthEducation]] = {
        "geographic_concentration": _build_geographic_concentration_education,
        "position_concentration": _build_position_concentration_education,
        "etf_overlap": _build_etf_overlap_education,
        "portfolio_risk": _build_portfolio_risk_education,
        "high_costs": _build_high_costs_education,
    }
    builder = builders.get(alert.type)
    if builder is None:
        return None
    return builder(alert, metrics)


def enrich_alerts_with_education(
    alerts: list[PortfolioHealthAlert],
    metrics: PortfolioHealthMetrics,
) -> list[PortfolioHealthAlert]:
    for alert in alerts:
        alert.education = build_alert_education(alert, metrics)
    return alerts


def _build_geographic_concentration_education(
    _alert: PortfolioHealthAlert,
    metrics: PortfolioHealthMetrics,
) -> PortfolioHealthEducation:
    usa_weight = metrics.geographic_exposure.get("usa", 0.0)
    europe_weight = metrics.geographic_exposure.get("europe", 0.0)
    emerging_weight = metrics.geographic_exposure.get("emerging", 0.0)
    return PortfolioHealthEducation(
        code="geographic_concentration",
        title="Esposizione geografica concentrata",
        what_it_means="Una parte molto ampia del portafoglio dipende dalla stessa area geografica, in questo caso dagli Stati Uniti.",
        why_it_matters="Quando un solo mercato pesa troppo, una fase negativa in quell'area puo' trascinare gran parte del portafoglio nella stessa direzione.",
        how_to_read_it=(
            f"Nel tuo caso gli USA pesano circa {usa_weight:.1f}%. "
            f"Confronta questo dato con Europa ({europe_weight:.1f}%) ed emergenti ({emerging_weight:.1f}%) "
            "per capire quanto il portafoglio sia sbilanciato."
        ),
        concept="Diversificazione geografica",
        copilot_prompts=[
            "Spiegami in modo semplice perche' l'esposizione USA e' alta",
            "Perche' questo sbilanciamento geografico conta davvero?",
            "Come potrei ridurre la concentrazione geografica del portafoglio?",
        ],
    )


def _build_position_concentration_education(
    alert: PortfolioHealthAlert,
    metrics: PortfolioHealthMetrics,
) -> PortfolioHealthEducation:
    details = alert.details or {}
    dominant = details.get("dominant_position") if isinstance(details, dict) else None
    if isinstance(dominant, dict):
        symbol = str(dominant.get("symbol") or "la posizione principale")
        weight = dominant.get("weight_pct")
        if isinstance(weight, (int, float)):
            how_to_read_it = (
                f"La posizione dominante e' {symbol} e pesa circa {weight:.1f}% del portafoglio. "
                "Se questa posizione si muove molto, l'impatto sul totale diventa immediatamente visibile."
            )
        else:
            how_to_read_it = (
                f"Controlla quanto pesa {symbol} rispetto alle altre prime posizioni. "
                "Se il distacco e' ampio, il portafoglio dipende troppo da un solo strumento."
            )
    else:
        how_to_read_it = (
            f"La posizione piu' grande pesa circa {metrics.max_position_weight:.1f}% del portafoglio. "
            "Confronta questo dato con le altre posizioni per vedere se una sola domina davvero il risultato finale."
        )

    return PortfolioHealthEducation(
        code="position_concentration",
        title="Portafoglio concentrato su una singola posizione",
        what_it_means="Una singola posizione pesa troppo rispetto al resto del portafoglio.",
        why_it_matters="Quando uno strumento domina, rischio e rendimento dipendono troppo dal suo andamento specifico e meno dalla qualita' complessiva della costruzione.",
        how_to_read_it=how_to_read_it,
        concept="Concentrazione",
        copilot_prompts=[
            "Spiegami in modo semplice il rischio di una posizione troppo grande",
            "Quanto incide davvero la posizione principale sul mio portafoglio?",
            "Cosa potrei sistemare per ridurre questa concentrazione?",
        ],
    )


def _build_etf_overlap_education(
    alert: PortfolioHealthAlert,
    metrics: PortfolioHealthMetrics,
) -> PortfolioHealthEducation:
    details = alert.details or {}
    pairs = details.get("pairs") if isinstance(details, dict) else None
    top_pair_note = "Controlla le coppie di ETF con sovrapposizione piu' alta nel dettaglio."
    if isinstance(pairs, list) and pairs:
        first_pair = pairs[0]
        if isinstance(first_pair, dict):
            left = first_pair.get("left")
            right = first_pair.get("right")
            overlap = first_pair.get("estimated_overlap_pct")
            if isinstance(left, dict) and isinstance(right, dict):
                left_symbol = str(left.get("symbol") or "ETF 1")
                right_symbol = str(right.get("symbol") or "ETF 2")
                if isinstance(overlap, (int, float)):
                    top_pair_note = (
                        f"La coppia {left_symbol}/{right_symbol} mostra una sovrapposizione stimata di circa {overlap:.1f}%. "
                        "Questo e' un buon punto di partenza per capire dove stai duplicando esposizione."
                    )

    return PortfolioHealthEducation(
        code="etf_overlap",
        title="ETF parzialmente sovrapposti",
        what_it_means="Due o piu' ETF presenti nel portafoglio espongono in parte agli stessi titoli o agli stessi segmenti di mercato.",
        why_it_matters="La sovrapposizione puo' dare l'impressione di essere diversificati, ma in realta' concentra il portafoglio sugli stessi driver di rischio.",
        how_to_read_it=(
            f"Il punteggio di overlap e' circa {metrics.overlap_score:.1f}%. "
            f"{top_pair_note}"
        ),
        concept="Sovrapposizione",
        copilot_prompts=[
            "Spiegami in modo semplice cosa significa overlap tra ETF",
            "Perche' questi ETF possono essere ridondanti?",
            "Qual e' la sovrapposizione che dovrei guardare per prima?",
        ],
    )


def _build_portfolio_risk_education(
    _alert: PortfolioHealthAlert,
    metrics: PortfolioHealthMetrics,
) -> PortfolioHealthEducation:
    volatility = metrics.portfolio_volatility or 0.0
    return PortfolioHealthEducation(
        code="portfolio_risk",
        title="Volatilita' del portafoglio elevata",
        what_it_means="Il portafoglio tende ad avere oscillazioni ampie nel tempo.",
        why_it_matters="Una volatilita' alta non significa automaticamente che il portafoglio sia sbagliato, ma implica movimenti piu' bruschi e una maggiore difficolta' nel reggere le fasi negative.",
        how_to_read_it=(
            f"La volatilita' stimata e' circa {volatility:.1f}%. "
            "Piu' questo valore sale, piu' devi aspettarti variazioni marcate del valore del portafoglio."
        ),
        concept="Volatilita'",
        copilot_prompts=[
            "Spiegami in modo semplice cosa vuol dire volatilita' alta",
            "Perche' la volatilita' del mio portafoglio e' elevata?",
            "Quali elementi del portafoglio possono aumentare di piu' il rischio?",
        ],
    )


def _build_high_costs_education(
    _alert: PortfolioHealthAlert,
    metrics: PortfolioHealthMetrics,
) -> PortfolioHealthEducation:
    weighted_ter = metrics.weighted_ter or 0.0
    return PortfolioHealthEducation(
        code="high_costs",
        title="Costo medio del portafoglio sopra il necessario",
        what_it_means="Le commissioni medie dei fondi presenti nel portafoglio sono relativamente alte rispetto a soluzioni simili piu' efficienti.",
        why_it_matters="I costi sembrano piccoli anno per anno, ma si accumulano nel tempo e riducono il rendimento netto che rimane all'investitore.",
        how_to_read_it=(
            f"Il TER medio ponderato e' circa {weighted_ter:.2f}%. "
            "Confronta soprattutto i fondi piu' pesanti: piccoli risparmi sui costi contano di piu' quando il peso in portafoglio e' alto."
        ),
        concept="TER",
        copilot_prompts=[
            "Spiegami in modo semplice cos'e' il TER",
            "Perche' i costi del mio portafoglio contano nel lungo periodo?",
            "Su quali fondi ha piu' senso controllare prima i costi?",
        ],
    )
