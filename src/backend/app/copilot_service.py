"""Portfolio Copilot – Multi-provider LLM streaming with agentic tool calling (Fase 2)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Generator

from pydantic import BaseModel

from .config import Settings
from .copilot_tools import TOOL_DEFINITIONS, execute_tool, format_tools_for_provider
from .performance_service import PerformanceService
from .repository import PortfolioRepository
from .services.portfolio_doctor import analyze_portfolio_health, run_monte_carlo_projection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agentic constants
# ---------------------------------------------------------------------------

MAX_TOOL_ROUNDS = 5
AGENTIC_TIMEOUT_S = 30

# ---------------------------------------------------------------------------
# Default models per provider
# ---------------------------------------------------------------------------

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
    "gemini": "gemini-2.0-flash",
    "openrouter": "deepseek/deepseek-chat",
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
# Agentic system prompt (Fase 2)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_AGENTIC = """\
Sei il Portfolio Copilot di Valore365, un assistente che aiuta persone comuni
a capire e ottimizzare i propri piccoli portafogli di investimento.

Il tuo utente tipico NON e' un professionista della finanza. Parla in modo
semplice, concreto e amichevole. Usa analogie quotidiane quando servono.

Hai accesso a diversi strumenti (tool) per ottenere dati dal portafoglio
dell'utente. Usali quando serve per dare risposte precise e basate sui dati.

Regole:
- Rispondi SOLO in italiano
- Usa SOLO dati ottenuti dai tool o dallo snapshot, MAI inventare numeri
- Non dare consulenza finanziaria personalizzata — dai informazioni e calcoli
- Quando suggerisci operazioni, mostra sempre i numeri concreti (importi, quote)
- Se l'utente chiede qualcosa che non puoi calcolare, dillo onestamente
- Spiega i concetti finanziari in modo semplice quando li usi
  (es. "Il drift e' quanto sei lontano dal tuo piano originale")
- Alla fine aggiungi: "⚠️ Supporto informativo, non consulenza finanziaria."

Formato risposta:
- Vai dritto al punto, niente introduzioni lunghe
- Usa **grassetto** per numeri importanti
- Usa tabelle quando confronti piu' asset
- Se suggerisci azioni, elencale come checklist

Ecco un riepilogo base del portafoglio:

{context}
"""

# ---------------------------------------------------------------------------
# Lightweight snapshot builder (for agentic mode — less tokens)
# ---------------------------------------------------------------------------

def build_portfolio_snapshot_light(
    repo: PortfolioRepository,
    portfolio_id: int,
    user_id: str,
) -> dict:
    """Build a minimal snapshot for the agentic system prompt.
    Detailed data is fetched on-demand via tool calls."""
    summary = repo.get_summary(portfolio_id, user_id)

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
    }

    # Resolve actual portfolio name
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
# Snapshot builder (full — for non-agentic / fallback mode)
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
    elif provider == "openrouter":
        return settings.openrouter_api_key
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
        elif provider == "openrouter":
            yield from _stream_openrouter(api_key, model, system_prompt, messages)
        elif provider == "local":
            yield from _stream_local(config.local_url, api_key, model, system_prompt, messages)
        else:
            raise ValueError(f"Provider non supportato: {provider}")

        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

    except Exception as exc:
        logger.exception("Copilot streaming error")
        yield _sse("error", _friendly_error(exc))


# ---------------------------------------------------------------------------
# Agentic streaming (Fase 2) — tool calling loop
# ---------------------------------------------------------------------------

def stream_copilot_response_agentic(
    config: CopilotConfig,
    snapshot: dict,
    messages: list[CopilotMessage],
    repo: PortfolioRepository,
    perf_service: PerformanceService,
    portfolio_id: int,
    user_id: str,
) -> Generator[str, None, None]:
    """Stream LLM response with tool-calling loop. Max MAX_TOOL_ROUNDS rounds."""
    system_prompt = SYSTEM_PROMPT_AGENTIC.format(
        context=json.dumps(snapshot, ensure_ascii=False, indent=2)
    )
    provider = config.provider
    tools = format_tools_for_provider(provider)
    start_time = time.monotonic()

    # Build initial message list in provider format
    conv_messages = [{"role": m.role, "content": m.content} for m in messages]

    try:
        for round_num in range(MAX_TOOL_ROUNDS):
            # Timeout check
            elapsed = time.monotonic() - start_time
            if elapsed > AGENTIC_TIMEOUT_S:
                yield _sse("error", "Timeout: la richiesta ha impiegato troppo tempo.")
                return

            # Call LLM with tools (non-streaming to inspect tool calls)
            tool_calls, text_content = _call_llm_with_tools(
                config, system_prompt, conv_messages, tools,
            )

            if tool_calls:
                # Emit thinking status
                yield _sse("thinking", f"Sto analizzando i dati ({round_num + 1})...")

                # Build assistant message with tool calls
                assistant_msg = _build_assistant_tool_message(provider, tool_calls, text_content)
                conv_messages.append(assistant_msg)

                # Execute each tool and append results
                for tc in tool_calls:
                    result = execute_tool(
                        tc["name"], tc["args"],
                        repo, perf_service, portfolio_id, user_id,
                    )
                    tool_result_msg = _build_tool_result_message(provider, tc["id"], tc["name"], result)
                    conv_messages.append(tool_result_msg)

                continue  # next round

            # No tool calls -> stream the final text response
            if text_content:
                # We already have the text, emit it
                yield _sse("text_delta", text_content)
            else:
                # Stream final response
                yield from _stream_final_response(config, system_prompt, conv_messages)

            yield _sse("done", "")
            return

        # Exhausted all rounds — do a final streaming call without tools
        yield _sse("thinking", "Sto preparando la risposta finale...")
        yield from _stream_final_response(config, system_prompt, conv_messages)
        yield _sse("done", "")

    except Exception as exc:
        logger.exception("Copilot agentic streaming error")
        yield _sse("error", _friendly_error(exc))


def _friendly_error(exc: Exception) -> str:
    """Convert provider exceptions to user-friendly Italian messages."""
    msg = str(exc).lower()
    if "429" in msg or "rate" in msg or "quota" in msg or "resource_exhausted" in msg:
        return (
            "Limite di utilizzo API raggiunto. "
            "Riprova tra qualche minuto oppure controlla il tuo piano sul provider AI."
        )
    if "401" in msg or "unauthorized" in msg or "invalid api key" in msg or "authentication" in msg:
        return "Chiave API non valida o scaduta. Controlla la configurazione nelle impostazioni."
    if "timeout" in msg or "timed out" in msg:
        return "Il servizio AI non ha risposto in tempo. Riprova tra poco."
    if "connection" in msg or "connect" in msg:
        return "Impossibile raggiungere il servizio AI. Verifica la connessione."
    return f"Errore dal servizio AI: {str(exc)[:200]}"


def _sse(event_type: str, content: str) -> str:
    """Format an SSE event."""
    return f"data: {json.dumps({'type': event_type, 'content': content}, ensure_ascii=False)}\n\n"


def _call_llm_with_tools(
    config: CopilotConfig,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
) -> tuple[list[dict], str]:
    """Call LLM with tools (non-streaming). Returns (tool_calls, text_content).

    Each tool_call dict: {"id": str, "name": str, "args": dict}
    """
    provider = config.provider

    if provider == "openai":
        return _call_openai_with_tools(config.api_key, config.model, system_prompt, messages, tools)
    elif provider == "anthropic":
        return _call_anthropic_with_tools(config.api_key, config.model, system_prompt, messages, tools)
    elif provider == "gemini":
        return _call_gemini_with_tools(config.api_key, config.model, system_prompt, messages, tools)
    elif provider == "openrouter":
        return _call_openai_with_tools(
            config.api_key, config.model, system_prompt, messages, tools,
            base_url="https://openrouter.ai/api/v1",
        )
    else:
        raise ValueError(f"Provider '{provider}' non supporta tool calling")


def _call_openai_with_tools(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict], tools: list[dict],
    base_url: str | None = None,
) -> tuple[list[dict], str]:
    """OpenAI / OpenRouter tool calling."""
    import openai

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = openai.OpenAI(**kwargs)

    oai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        oai_messages.append(msg)

    response = client.chat.completions.create(
        model=model, max_tokens=2048, messages=oai_messages, tools=tools,
    )
    choice = response.choices[0]
    text_content = choice.message.content or ""

    tool_calls = []
    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "args": json.loads(tc.function.arguments) if tc.function.arguments else {},
            })

    return tool_calls, text_content


def _call_anthropic_with_tools(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict], tools: list[dict],
) -> tuple[list[dict], str]:
    """Anthropic tool calling."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model, max_tokens=2048, system=system_prompt,
        messages=messages, tools=tools,
    )

    tool_calls = []
    text_content = ""

    for block in response.content:
        if block.type == "text":
            text_content += block.text
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "args": block.input if isinstance(block.input, dict) else {},
            })

    return tool_calls, text_content


def _call_gemini_with_tools(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict], tools: list[dict],
) -> tuple[list[dict], str]:
    """Gemini tool calling."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    # Build Gemini tool declarations
    function_declarations = []
    for t in tools:
        func = t.get("function", t)
        fd = types.FunctionDeclaration(
            name=func["name"],
            description=func["description"],
            parameters=func.get("parameters", {}),
        )
        function_declarations.append(fd)

    gemini_tools = [types.Tool(function_declarations=function_declarations)]

    contents = [
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Capito, sono pronto ad aiutarti."}]},
    ]
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "model"
        parts = msg.get("parts", [{"text": msg.get("content", "")}])
        contents.append({"role": role, "parts": parts})

    response = client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(
            max_output_tokens=2048,
            tools=gemini_tools,
        ),
    )

    tool_calls = []
    text_content = ""

    if response.candidates:
        for part in response.candidates[0].content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append({
                    "id": fc.name,  # Gemini uses name as id
                    "name": fc.name,
                    "args": dict(fc.args) if fc.args else {},
                })
            elif hasattr(part, "text") and part.text:
                text_content += part.text

    return tool_calls, text_content


def _build_assistant_tool_message(provider: str, tool_calls: list[dict], text_content: str) -> dict:
    """Build the assistant message that contains tool calls, for conversation history."""
    if provider == "anthropic":
        content = []
        if text_content:
            content.append({"type": "text", "text": text_content})
        for tc in tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["args"],
            })
        return {"role": "assistant", "content": content}

    elif provider == "gemini":
        parts = []
        if text_content:
            parts.append({"text": text_content})
        for tc in tool_calls:
            parts.append({
                "function_call": {"name": tc["name"], "args": tc["args"]},
            })
        return {"role": "model", "parts": parts}

    else:  # openai / openrouter
        msg: dict = {
            "role": "assistant",
            "content": text_content or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
                for tc in tool_calls
            ],
        }
        return msg


def _build_tool_result_message(provider: str, tool_id: str, tool_name: str, result: dict) -> dict:
    """Build the tool result message for conversation history."""
    result_str = json.dumps(result, ensure_ascii=False)

    if provider == "anthropic":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_str,
                }
            ],
        }

    elif provider == "gemini":
        return {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "name": tool_name,
                        "response": result,
                    },
                }
            ],
        }

    else:  # openai / openrouter
        return {
            "role": "tool",
            "tool_call_id": tool_id,
            "content": result_str,
        }


def _stream_final_response(
    config: CopilotConfig,
    system_prompt: str,
    messages: list[dict],
) -> Generator[str, None, None]:
    """Stream the final text response (no tools) from the LLM."""
    provider = config.provider
    api_key = config.api_key
    model = config.model

    # Convert messages to CopilotMessage-like for reuse of existing streaming
    # For the final response, we pass the full conversation including tool results
    if provider == "openai":
        yield from _stream_openai_raw(api_key, model, system_prompt, messages)
    elif provider == "anthropic":
        yield from _stream_anthropic_raw(api_key, model, system_prompt, messages)
    elif provider == "gemini":
        yield from _stream_gemini_raw(api_key, model, system_prompt, messages)
    elif provider == "openrouter":
        yield from _stream_openai_raw(
            api_key, model, system_prompt, messages,
            base_url="https://openrouter.ai/api/v1",
        )


def _stream_openai_raw(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict], base_url: str | None = None,
) -> Generator[str, None, None]:
    """Stream final response from OpenAI/OpenRouter with full message history."""
    import openai

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = openai.OpenAI(**kwargs)

    oai_messages = [{"role": "system", "content": system_prompt}]
    oai_messages.extend(messages)

    stream = client.chat.completions.create(
        model=model, max_tokens=2048, stream=True, messages=oai_messages,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield _sse("text_delta", delta.content)


def _stream_anthropic_raw(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict],
) -> Generator[str, None, None]:
    """Stream final response from Anthropic with full message history."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    with client.messages.stream(
        model=model, max_tokens=2048, system=system_prompt, messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield _sse("text_delta", text)


def _stream_gemini_raw(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict],
) -> Generator[str, None, None]:
    """Stream final response from Gemini with full message history."""
    from google import genai

    client = genai.Client(api_key=api_key)

    contents = [
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Capito, sono pronto ad aiutarti."}]},
    ]
    contents.extend(messages)

    response = client.models.generate_content(
        model=model, contents=contents, config={"max_output_tokens": 2048},
    )
    if response.text:
        yield _sse("text_delta", response.text)


# ---------------------------------------------------------------------------
# Legacy streaming (non-agentic — Fase 1, used as fallback)
# ---------------------------------------------------------------------------

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


def _stream_openrouter(
    api_key: str, model: str, system_prompt: str, messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    """Stream from OpenRouter (OpenAI-compatible API)."""
    import openai

    client = openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
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
