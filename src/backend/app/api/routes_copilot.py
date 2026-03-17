from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError
from ..copilot_service import (
    CopilotChatRequest,
    build_aggregate_snapshot_light,
    build_portfolio_snapshot,
    build_portfolio_snapshot_light,
    resolve_copilot_config,
    stream_copilot_response,
    stream_copilot_response_agentic,
)
from ..repository import PortfolioRepository


def register_copilot_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    settings: object,
    performance_service: object,
) -> None:

    @router.get("/copilot/status")
    def copilot_status(_auth: AuthContext = Depends(require_auth_rate_limited)) -> dict:
        user_settings = repo.get_user_settings(_auth.user_id)
        user_key_enc = repo.get_user_copilot_api_key_enc(_auth.user_id)
        config = resolve_copilot_config(
            settings,
            user_provider=user_settings.copilot_provider,
            user_model=user_settings.copilot_model,
            user_api_key_enc=user_key_enc,
        )
        return {
            "available": config is not None,
            "provider": config.provider if config else None,
            "model": config.model if config else None,
            "source": "user" if (config and user_settings.copilot_api_key_set) else ("server" if config else None),
        }

    @router.post("/copilot/chat")
    def copilot_chat(
        payload: CopilotChatRequest,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ):
        user_settings = repo.get_user_settings(_auth.user_id)
        user_key_enc = repo.get_user_copilot_api_key_enc(_auth.user_id)
        config = resolve_copilot_config(
            settings,
            user_provider=user_settings.copilot_provider,
            user_model=user_settings.copilot_model,
            user_api_key_enc=user_key_enc,
        )
        if config is None:
            raise AppError(
                code="copilot_unavailable",
                message="Copilot non configurato: API key mancante",
                status_code=503,
            )

        # Use agentic flow for providers that support tool calling
        is_aggregate = payload.portfolio_ids and len(payload.portfolio_ids) > 1
        if config.provider in ("openai", "anthropic", "gemini", "openrouter"):
            if is_aggregate:
                snapshot = build_aggregate_snapshot_light(
                    repo, payload.portfolio_ids, _auth.user_id,
                )
            else:
                snapshot = build_portfolio_snapshot_light(
                    repo, payload.portfolio_id, _auth.user_id,
                )
            generator = stream_copilot_response_agentic(
                config, snapshot, payload.messages,
                repo, performance_service, payload.portfolio_id, _auth.user_id,
            )
        else:
            # Fallback for local providers without tool calling
            snapshot = build_portfolio_snapshot(
                repo, performance_service, payload.portfolio_id, _auth.user_id,
            )
            generator = stream_copilot_response(config, snapshot, payload.messages)

        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
