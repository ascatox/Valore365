"""Copilot streaming response generators (SSE): legacy and agentic."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Generator

from ..copilot_tools import (
    build_tool_availability_block,
    execute_tool,
    format_tools_for_provider,
    get_allowed_tool_names_for_page_context,
)
from ..services.performance_service import PerformanceService
from ..repository import PortfolioRepository
from .config import CopilotConfig
from .models import CopilotMessage
from .providers import (
    _build_assistant_tool_message,
    _build_tool_result_message,
    _call_llm_with_tools,
    _sse,
    _stream_anthropic,
    _stream_final_response,
    _stream_gemini,
    _stream_local,
    _stream_openai,
    _stream_openrouter,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agentic constants
# ---------------------------------------------------------------------------

MAX_TOOL_ROUNDS = 5
AGENTIC_TIMEOUT_S = 120

# ---------------------------------------------------------------------------
# System prompts (loaded once at import time)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "copilot_system.txt").read_text(encoding="utf-8")
SYSTEM_PROMPT_AGENTIC = (Path(__file__).resolve().parent.parent / "prompts" / "copilot_system_agentic.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Friendly error helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Legacy streaming (non-agentic -- Fase 1)
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
# Page-context hints for agentic mode
# ---------------------------------------------------------------------------

_PAGE_CONTEXT_HINTS: dict[str, str] = {
    "dashboard": (
        "L'utente sta guardando la Dashboard. Concentrati su: panoramica generale, "
        "variazione giornaliera, migliori/peggiori performer, e suggerimenti rapidi."
    ),
    "portfolio": (
        "L'utente sta guardando il dettaglio Portafoglio. Concentrati su: posizioni, "
        "pesi, drift dal target, ribilanciamento, e analisi singole posizioni."
    ),
    "doctor": (
        "L'utente sta guardando il Portfolio Doctor. Concentrati su: salute del portafoglio, "
        "diversificazione, costi (TER), overlap, rischio, e suggerimenti di miglioramento. "
        "Usa get_portfolio_health, get_cost_breakdown, get_stress_test per dati specifici."
    ),
    "fire": (
        "L'utente sta guardando la sezione FIRE. Concentrati su: proiezioni a lungo termine, "
        "reddito passivo, dividendi, tasso di prelievo sicuro, e tempo al FIRE. "
        "Usa get_income_projection, get_monte_carlo, get_dividend_summary."
    ),
    "xray": (
        "L'utente sta guardando l'X-Ray del portafoglio. Concentrati su: esposizione "
        "sottostante, diversificazione geografica/settoriale, concentrazione su singoli titoli. "
        "Usa get_xray_summary per dati dettagliati."
    ),
    "transactions": (
        "L'utente sta guardando le Transazioni. Concentrati su: cronologia operazioni, "
        "dividendi ricevuti, costi di transazione. Usa get_recent_transactions, get_dividend_summary."
    ),
}


def _build_page_context_block(page_context: str | None) -> str:
    """Build a context hint block for the system prompt based on the current page."""
    if not page_context:
        return ""
    hint = _PAGE_CONTEXT_HINTS.get(page_context, "")
    if not hint:
        return ""
    return f"\n\n--- CONTESTO PAGINA ---\n{hint}\n--- FINE CONTESTO PAGINA ---"


def _build_snapshot_guidance_block(snapshot: dict) -> str:
    available_data: list[str] = []
    avoid_tools: list[str] = ["get_portfolio_summary", "get_cash_balance"]

    portfolio_section = snapshot.get("portfolio") or snapshot.get("aggregate_portfolio") or {}
    if isinstance(portfolio_section, dict):
        if portfolio_section.get("weighted_ter_pct") is not None:
            available_data.append("TER ponderato")

    if "positions" in snapshot:
        available_data.append("posizioni e pesi principali")
        avoid_tools.append("get_positions")
    if "target_drift" in snapshot:
        available_data.append("drift dal target")
        avoid_tools.append("get_target_drift")
    if "performance" in snapshot:
        available_data.append("performance sintetica")
        avoid_tools.append("get_performance")
    if "fire" in snapshot:
        available_data.append("impostazioni FIRE")
    if "pac_plans" in snapshot:
        available_data.append("PAC attivi")

    if not available_data:
        return ""

    data_list = ", ".join(available_data)
    avoid_list = ", ".join(avoid_tools)
    return (
        "--- DATI GIA' PRESENTI NELLO SNAPSHOT ---\n"
        f"Hai gia': {data_list}.\n"
        f"Usa prima questi dati e non chiamare: {avoid_list}.\n"
        "--- FINE DATI GIA' PRESENTI ---"
    )


# ---------------------------------------------------------------------------
# Agentic streaming (Fase 2) -- tool calling loop
# ---------------------------------------------------------------------------

def stream_copilot_response_agentic(
    config: CopilotConfig,
    snapshot: dict,
    messages: list[CopilotMessage],
    repo: PortfolioRepository,
    perf_service: PerformanceService,
    portfolio_id: int,
    user_id: str,
    *,
    finance_client: object | None = None,
    justetf_client: object | None = None,
    page_context: str | None = None,
) -> Generator[str, None, None]:
    """Stream LLM response with tool-calling loop. Max MAX_TOOL_ROUNDS rounds."""
    allowed_tool_names = get_allowed_tool_names_for_page_context(page_context)
    system_prompt = SYSTEM_PROMPT_AGENTIC.format(
        context=json.dumps(snapshot, ensure_ascii=False, indent=2),
        page_context_block=_build_page_context_block(page_context),
        snapshot_guidance_block=_build_snapshot_guidance_block(snapshot),
        tool_availability_block=build_tool_availability_block(page_context),
    )
    provider = config.provider
    tools = format_tools_for_provider(provider, allowed_tool_names=allowed_tool_names)
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
                        finance_client=finance_client,
                        justetf_client=justetf_client,
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

        # Exhausted all rounds -- do a final streaming call without tools
        yield _sse("thinking", "Sto preparando la risposta finale...")
        yield from _stream_final_response(config, system_prompt, conv_messages)
        yield _sse("done", "")

    except Exception as exc:
        logger.exception("Copilot agentic streaming error")
        yield _sse("error", _friendly_error(exc))
