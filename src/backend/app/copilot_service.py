"""Portfolio Copilot – MVP explain-only with multi-provider LLM streaming."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Generator

from pydantic import BaseModel

from .config import Settings
from .performance_service import PerformanceService
from .repository import PortfolioRepository
from .services.portfolio_doctor import analyze_portfolio_health, run_monte_carlo_projection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default models per provider
# ---------------------------------------------------------------------------

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
    "gemini": "gemini-2.0-flash",
    "local": "llama3.2:3b",
}

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CopilotMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class CopilotChatRequest(BaseModel):
    portfolio_id: int
    messages: list[CopilotMessage]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Sei il Portfolio Copilot di Valore365, un assistente informativo per investitori.

Regole:
- Rispondi SOLO in italiano
- Usa SOLO i dati forniti nello snapshot qui sotto, non inventare mai numeri o fatti
- Non dare consulenza finanziaria personalizzata
- Se non hai dati sufficienti, dillo esplicitamente
- Sii sintetico, diretto e chiaro
- Cita sempre i numeri quando li usi
- Distingui fatti da interpretazioni
- Alla fine di ogni risposta aggiungi: "⚠️ Supporto informativo, non consulenza finanziaria."

Formato risposta consigliato:
- **Sintesi** (2-3 frasi)
- **Numeri chiave** (lista breve)
- **Cosa osservare** (se pertinente)

Ecco i dati del portafoglio dell'utente:

{context}
"""

# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------

def build_portfolio_snapshot(
    repo: PortfolioRepository,
    perf_service: PerformanceService,
    portfolio_id: int,
    user_id: str,
) -> dict:
    """Build a compact JSON snapshot of the portfolio for the LLM context."""
    summary = repo.get_summary(portfolio_id, user_id)
    positions = repo.get_positions(portfolio_id, user_id)
    allocation = repo.get_allocation(portfolio_id, user_id)

    # Target allocation (may not exist)
    try:
        target_alloc = repo.list_portfolio_target_allocations(portfolio_id, user_id)
    except Exception:
        target_alloc = []

    # Best/worst performers
    try:
        target_perf = repo.get_portfolio_target_performance(portfolio_id, user_id)
        best = {"symbol": target_perf.best.symbol, "day_change_pct": target_perf.best.day_change_pct} if target_perf.best else None
        worst = {"symbol": target_perf.worst.symbol, "day_change_pct": target_perf.worst.day_change_pct} if target_perf.worst else None
    except Exception:
        best = worst = None

    # Performance summary
    perf_data = {}
    for period in ("1m", "3m", "ytd", "1y"):
        try:
            ps = perf_service.get_performance_summary(portfolio_id, user_id, period)
            perf_data[f"twr_{period}"] = round(ps.twr.twr_pct, 2) if ps.twr.twr_pct is not None else None
        except Exception:
            pass

    # Limit positions to top 30 by weight
    sorted_positions = sorted(positions, key=lambda p: p.weight, reverse=True)[:30]
    pos_list = [
        {
            "symbol": p.symbol,
            "name": p.name,
            "weight": round(p.weight, 2),
            "market_value": round(p.market_value, 2),
            "unrealized_pl_pct": round(p.unrealized_pl_pct, 2),
            "day_change_pct": round(p.day_change_pct, 2) if p.day_change_pct else 0,
        }
        for p in sorted_positions
    ]

    # Target drift
    alloc_map = {a.asset_id: a.weight_pct for a in allocation}
    drift_list = []
    for ta in target_alloc:
        current = alloc_map.get(ta.asset_id, 0.0)
        drift_list.append({
            "symbol": ta.symbol,
            "current_weight": round(current, 2),
            "target_weight": round(ta.weight_pct, 2),
            "drift": round(current - ta.weight_pct, 2),
        })

    snapshot = {
        "portfolio": {
            "name": f"Portfolio #{portfolio_id}",
            "base_currency": summary.base_currency,
            "market_value": round(summary.market_value, 2),
            "cost_basis": round(summary.cost_basis, 2),
            "unrealized_pl": round(summary.unrealized_pl, 2),
            "unrealized_pl_pct": round(summary.unrealized_pl_pct, 2),
            "day_change": round(summary.day_change, 2),
            "day_change_pct": round(summary.day_change_pct, 2),
            "cash_balance": round(summary.cash_balance, 2),
        },
        "positions": pos_list,
        "performance": perf_data,
    }

    try:
        doctor = analyze_portfolio_health(repo, portfolio_id, user_id)
        snapshot["doctor"] = {
            "score": doctor.score,
            "risk_level": doctor.summary.risk_level,
            "diversification": doctor.summary.diversification,
            "overlap": doctor.summary.overlap,
            "cost_efficiency": doctor.summary.cost_efficiency,
            "max_position_weight": round(doctor.metrics.max_position_weight, 2),
            "overlap_score": round(doctor.metrics.overlap_score, 2),
            "portfolio_volatility": round(doctor.metrics.portfolio_volatility, 2) if doctor.metrics.portfolio_volatility is not None else None,
            "weighted_ter": round(doctor.metrics.weighted_ter, 2) if doctor.metrics.weighted_ter is not None else None,
            "top_alerts": [alert.message for alert in doctor.alerts[:5]],
            "top_suggestions": [suggestion.message for suggestion in doctor.suggestions[:5]],
        }
    except Exception:
        pass

    try:
        monte_carlo = run_monte_carlo_projection(repo, portfolio_id, user_id)
        snapshot["doctor_monte_carlo"] = {
            "annualized_mean_return_pct": round(monte_carlo.annualized_mean_return_pct, 2),
            "annualized_volatility_pct": round(monte_carlo.annualized_volatility_pct, 2),
            "horizons": monte_carlo.horizons,
            "projections": [
                {
                    "year": projection.year,
                    "p25": projection.p25,
                    "p50": projection.p50,
                    "p75": projection.p75,
                }
                for projection in monte_carlo.projections[:10]
                if projection.year > 0
            ],
        }
    except Exception:
        pass

    if drift_list:
        snapshot["target_drift"] = drift_list
    if best:
        snapshot["best_performer"] = best
    if worst:
        snapshot["worst_performer"] = worst

    # Replace portfolio name with actual name
    try:
        portfolios = repo.list_portfolios(user_id)
        for p in portfolios:
            if p.id == portfolio_id:
                snapshot["portfolio"]["name"] = p.name
                break
    except Exception:
        pass

    return snapshot


# ---------------------------------------------------------------------------
# Provider helpers
# ---------------------------------------------------------------------------

@dataclass
class CopilotConfig:
    """Resolved copilot configuration (user-level or server-level)."""
    provider: str
    model: str
    api_key: str
    local_url: str = ""


def _decrypt_api_key(encrypted: str, settings: Settings) -> str:
    """Decrypt a Fernet-encrypted API key. Returns empty string on failure."""
    if not encrypted or not settings.copilot_encryption_key:
        return ""
    try:
        from cryptography.fernet import Fernet
        f = Fernet(settings.copilot_encryption_key.encode())
        return f.decrypt(encrypted.encode()).decode()
    except Exception:
        logger.warning("Failed to decrypt user API key")
        return ""


def encrypt_api_key(plaintext: str, settings: Settings) -> str:
    """Encrypt an API key with Fernet. Returns empty string if no encryption key."""
    if not plaintext or not settings.copilot_encryption_key:
        return ""
    from cryptography.fernet import Fernet
    f = Fernet(settings.copilot_encryption_key.encode())
    return f.encrypt(plaintext.encode()).decode()


def resolve_copilot_config(
    settings: Settings,
    user_provider: str = "",
    user_model: str = "",
    user_api_key_enc: str = "",
) -> CopilotConfig | None:
    """Resolve copilot config: user key first, then server fallback.

    Returns None if no valid configuration is available.
    """
    # 1. Try user-level config
    if user_provider and user_api_key_enc:
        decrypted = _decrypt_api_key(user_api_key_enc, settings)
        if decrypted:
            model = user_model or _DEFAULT_MODELS.get(user_provider, "gpt-4o-mini")
            return CopilotConfig(
                provider=user_provider,
                model=model,
                api_key=decrypted,
                local_url=settings.copilot_local_url if user_provider == "local" else "",
            )

    # 2. Fallback to server-level config
    provider = settings.copilot_provider
    if not provider:
        return None
    api_key = _get_server_api_key(settings)
    if not api_key:
        return None
    model = settings.copilot_model or _DEFAULT_MODELS.get(provider, "gpt-4o-mini")
    return CopilotConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        local_url=settings.copilot_local_url if provider == "local" else "",
    )


def _get_server_api_key(settings: Settings) -> str:
    """Return the server-level API key for the configured provider."""
    provider = settings.copilot_provider
    if provider == "openai":
        return settings.openai_api_key
    elif provider == "anthropic":
        return settings.anthropic_api_key
    elif provider == "gemini":
        return settings.gemini_api_key
    elif provider == "local":
        return settings.copilot_local_api_key or "not-needed"
    return ""


def _get_model(settings: Settings) -> str:
    """Return the model name, falling back to provider default (for status endpoint)."""
    if settings.copilot_model:
        return settings.copilot_model
    return _DEFAULT_MODELS.get(settings.copilot_provider, "gpt-4o-mini")


def is_copilot_available(settings: Settings, user_provider: str = "", user_api_key_enc: str = "") -> bool:
    """Check if the copilot is available (user key or server key)."""
    return resolve_copilot_config(settings, user_provider=user_provider, user_api_key_enc=user_api_key_enc) is not None


# ---------------------------------------------------------------------------
# Streaming response generator (SSE) — multi-provider
# ---------------------------------------------------------------------------

def stream_copilot_response(
    config: CopilotConfig,
    snapshot: dict,
    messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    """Stream LLM response as SSE events. Supports OpenAI, Anthropic, Gemini."""
    system_prompt = SYSTEM_PROMPT.format(context=json.dumps(snapshot, ensure_ascii=False, indent=2))
    provider = config.provider
    api_key = config.api_key
    model = config.model

    try:
        if provider == "openai":
            yield from _stream_openai(api_key, model, system_prompt, messages)
        elif provider == "anthropic":
            yield from _stream_anthropic(api_key, model, system_prompt, messages)
        elif provider == "gemini":
            yield from _stream_gemini(api_key, model, system_prompt, messages)
        elif provider == "local":
            yield from _stream_local(config.local_url, api_key, model, system_prompt, messages)
        else:
            raise ValueError(f"Provider non supportato: {provider}")

        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

    except Exception as exc:
        logger.exception("Copilot streaming error")
        error_event = json.dumps({"type": "error", "content": str(exc)}, ensure_ascii=False)
        yield f"data: {error_event}\n\n"


def _stream_openai(
    api_key: str, model: str, system_prompt: str, messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    import openai

    client = openai.OpenAI(api_key=api_key)
    openai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        openai_messages.append({"role": msg.role, "content": msg.content})

    stream = client.chat.completions.create(
        model=model, max_tokens=2048, stream=True, messages=openai_messages,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield f"data: {json.dumps({'type': 'text_delta', 'content': delta.content}, ensure_ascii=False)}\n\n"


def _stream_anthropic(
    api_key: str, model: str, system_prompt: str, messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    anthro_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

    with client.messages.stream(
        model=model, max_tokens=2048, system=system_prompt, messages=anthro_messages,
    ) as stream:
        for text in stream.text_stream:
            yield f"data: {json.dumps({'type': 'text_delta', 'content': text}, ensure_ascii=False)}\n\n"


def _stream_gemini(
    api_key: str, model: str, system_prompt: str, messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    from google import genai

    client = genai.Client(api_key=api_key)
    contents = [{"role": "user", "parts": [{"text": system_prompt}]}, {"role": "model", "parts": [{"text": "Capito, sono pronto ad aiutarti."}]}]
    for msg in messages:
        role = "user" if msg.role == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.content}]})

    response = client.models.generate_content(
        model=model, contents=contents, config={"max_output_tokens": 2048},
    )
    # Gemini returns full response, emit as single chunk
    if response.text:
        yield f"data: {json.dumps({'type': 'text_delta', 'content': response.text}, ensure_ascii=False)}\n\n"


def _stream_local(
    local_url: str, api_key: str, model: str, system_prompt: str, messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    """Stream from a local LLM server exposing an OpenAI-compatible API (Ollama, LM Studio, etc.)."""
    import openai

    client = openai.OpenAI(
        base_url=local_url or "http://localhost:11434/v1",
        api_key=api_key or "not-needed",
    )
    openai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        openai_messages.append({"role": msg.role, "content": msg.content})

    stream = client.chat.completions.create(
        model=model, max_tokens=2048, stream=True, messages=openai_messages,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield f"data: {json.dumps({'type': 'text_delta', 'content': delta.content}, ensure_ascii=False)}\n\n"
