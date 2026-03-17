from .instant_portfolio_analyzer import register_instant_portfolio_analyzer_routes
from .portfolio_health import register_portfolio_health_routes
from .routes_portfolio import register_portfolio_routes
from .routes_assets import register_assets_routes
from .routes_transactions import register_transactions_routes
from .routes_pricing import register_pricing_routes
from .routes_analytics import register_analytics_routes
from .routes_rebalancing import register_rebalancing_routes
from .routes_markets import register_markets_routes
from .routes_cash import register_cash_routes
from .routes_csv import register_csv_routes
from .routes_pac import register_pac_routes
from .routes_copilot import register_copilot_routes

__all__ = [
    "register_instant_portfolio_analyzer_routes",
    "register_portfolio_health_routes",
    "register_portfolio_routes",
    "register_assets_routes",
    "register_transactions_routes",
    "register_pricing_routes",
    "register_analytics_routes",
    "register_rebalancing_routes",
    "register_markets_routes",
    "register_cash_routes",
    "register_csv_routes",
    "register_pac_routes",
    "register_copilot_routes",
]
