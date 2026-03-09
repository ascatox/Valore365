from fastapi import APIRouter

from ..errors import AppError
from ..models import ErrorResponse
from ..repository import PortfolioRepository
from ..schemas.instant_portfolio_analyzer import InstantAnalyzeRequest, InstantAnalyzeResponse
from ..services.instant_portfolio_analyzer import InstantPortfolioAnalysisError, analyze_public_portfolio


def register_instant_portfolio_analyzer_routes(router: APIRouter, repo: PortfolioRepository) -> None:
    @router.post(
        "/public/portfolio/analyze",
        response_model=InstantAnalyzeResponse,
        responses={400: {"model": ErrorResponse}},
    )
    def analyze_portfolio(payload: InstantAnalyzeRequest) -> InstantAnalyzeResponse:
        try:
            return analyze_public_portfolio(repo, payload)
        except InstantPortfolioAnalysisError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400, details=exc.details) from exc
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc
