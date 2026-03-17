from sqlalchemy.engine import Engine

from ._base import (
    AssetMeta,
    BaseRepositoryMixin,
    PortfolioData,
    PositionDelta,
    PricingAsset,
    _finite,
)
from ._admin import AdminMixin
from ._target_alloc import TargetAllocationMixin
from ._portfolio_crud import PortfolioCrudMixin
from ._asset_crud import AssetCrudMixin
from ._transactions import TransactionsMixin
from ._positions import PositionsMixin
from ._summary import SummaryMixin
from ._search_pricing import SearchPricingMixin
from ._utilities import UtilitiesMixin
from ._pac import PacMixin


class PortfolioRepository(
    AdminMixin,
    TargetAllocationMixin,
    PortfolioCrudMixin,
    AssetCrudMixin,
    TransactionsMixin,
    PositionsMixin,
    SummaryMixin,
    SearchPricingMixin,
    UtilitiesMixin,
    PacMixin,
    BaseRepositoryMixin,
):
    def __init__(self, engine: Engine) -> None:
        self.engine = engine


__all__ = [
    "PortfolioRepository",
    "PortfolioData",
    "PricingAsset",
    "AssetMeta",
    "PositionDelta",
    "_finite",
]
