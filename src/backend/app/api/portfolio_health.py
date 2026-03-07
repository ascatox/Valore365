from fastapi import APIRouter, Depends

from ..auth import AuthContext, require_auth
from ..errors import AppError
from ..models import ErrorResponse
from ..repository import PortfolioRepository
from ..schemas.portfolio_doctor import PortfolioHealthResponse
from ..services.portfolio_doctor import analyze_portfolio_health


def register_portfolio_health_routes(router: APIRouter, repo: PortfolioRepository) -> None:
    @router.get(
        "/portfolios/{portfolio_id}/health",
        response_model=PortfolioHealthResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_portfolio_health(
        portfolio_id: int,
        _auth: AuthContext = Depends(require_auth),
    ) -> PortfolioHealthResponse:
        try:
            return analyze_portfolio_health(repo, portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc
