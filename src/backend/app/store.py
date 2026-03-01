from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from .models import AllocationItem, PortfolioSummary, Position, TimeSeriesPoint, TransactionCreate, TransactionRead


@dataclass
class Asset:
    id: int
    symbol: str
    name: str
    quote_currency: str


@dataclass
class Portfolio:
    id: int
    name: str
    base_currency: str


class InMemoryStore:
    def __init__(self) -> None:
        self.portfolios = {1: Portfolio(id=1, name="Valore365 Portfolio", base_currency="EUR")}
        self.assets = {
            1: Asset(id=1, symbol="AAPL", name="Apple Inc.", quote_currency="USD"),
            2: Asset(id=2, symbol="MSFT", name="Microsoft Corp.", quote_currency="USD"),
            3: Asset(id=3, symbol="VWCE", name="Vanguard FTSE All-World", quote_currency="EUR"),
        }
        self.live_prices = {1: 189.40, 2: 421.90, 3: 123.35}
        self.transactions: list[TransactionRead] = []
        self.tx_id = 1

    def create_transaction(self, payload: TransactionCreate) -> TransactionRead:
        if payload.portfolio_id not in self.portfolios:
            raise ValueError("Portfolio non trovato")
        if payload.asset_id not in self.assets:
            raise ValueError("Asset non trovato")
        if payload.side not in {"buy", "sell"}:
            raise ValueError("side deve essere buy o sell")

        if payload.side == "sell":
            qty = self._current_quantity(payload.portfolio_id, payload.asset_id)
            if payload.quantity > qty:
                raise ValueError("Quantita insufficiente per sell")

        tx = TransactionRead(id=self.tx_id, **payload.model_dump())
        self.transactions.append(tx)
        self.tx_id += 1
        return tx

    def get_positions(self, portfolio_id: int) -> list[Position]:
        self._ensure_portfolio(portfolio_id)
        grouped = self._grouped_lots(portfolio_id)
        positions: list[Position] = []

        for asset_id, values in grouped.items():
            qty = values["quantity"]
            if qty <= 0:
                continue
            avg_cost = values["cost"] / qty if qty else 0
            price = self.live_prices.get(asset_id, avg_cost)
            market_value = qty * price
            cost_basis = qty * avg_cost
            pl = market_value - cost_basis
            pl_pct = (pl / cost_basis * 100) if cost_basis else 0
            asset = self.assets[asset_id]
            positions.append(
                Position(
                    asset_id=asset_id,
                    symbol=asset.symbol,
                    quantity=round(qty, 8),
                    avg_cost=round(avg_cost, 4),
                    market_price=round(price, 4),
                    market_value=round(market_value, 2),
                    unrealized_pl=round(pl, 2),
                    unrealized_pl_pct=round(pl_pct, 2),
                )
            )

        positions.sort(key=lambda p: p.market_value, reverse=True)
        return positions

    def get_summary(self, portfolio_id: int) -> PortfolioSummary:
        self._ensure_portfolio(portfolio_id)
        positions = self.get_positions(portfolio_id)
        market_value = sum(p.market_value for p in positions)
        cost_basis = sum(p.quantity * p.avg_cost for p in positions)
        pl = market_value - cost_basis
        pl_pct = (pl / cost_basis * 100) if cost_basis else 0

        return PortfolioSummary(
            portfolio_id=portfolio_id,
            base_currency=self.portfolios[portfolio_id].base_currency,
            market_value=round(market_value, 2),
            cost_basis=round(cost_basis, 2),
            unrealized_pl=round(pl, 2),
            unrealized_pl_pct=round(pl_pct, 2),
        )

    def get_timeseries(self, portfolio_id: int, range_value: str, interval: str) -> list[TimeSeriesPoint]:
        self._ensure_portfolio(portfolio_id)
        if range_value != "1y" or interval != "1d":
            raise ValueError("Solo range=1y e interval=1d supportati in V1")

        today = date.today()
        base_positions = self.get_positions(portfolio_id)
        current_value = sum(p.market_value for p in base_positions)
        if current_value == 0:
            return [
                TimeSeriesPoint(date=(today - timedelta(days=offset)).isoformat(), market_value=0.0)
                for offset in range(364, -1, -1)
            ]

        points: list[TimeSeriesPoint] = []
        for idx, offset in enumerate(range(364, -1, -1)):
            d = today - timedelta(days=offset)
            trend = 0.88 + (idx / 364.0) * 0.24
            value = round(current_value * trend, 2)
            points.append(TimeSeriesPoint(date=d.isoformat(), market_value=value))
        return points

    def get_allocation(self, portfolio_id: int) -> list[AllocationItem]:
        positions = self.get_positions(portfolio_id)
        total = sum(p.market_value for p in positions)
        if total == 0:
            return []
        return [
            AllocationItem(
                asset_id=p.asset_id,
                symbol=p.symbol,
                market_value=p.market_value,
                weight_pct=round(p.market_value / total * 100, 2),
            )
            for p in positions
        ]

    def search_assets(self, query: str) -> list[dict[str, str]]:
        q = query.lower().strip()
        if not q:
            return []
        results: list[dict[str, str]] = []
        for asset in self.assets.values():
            isin = getattr(asset, 'isin', '') or ''
            if q in asset.symbol.lower() or q in asset.name.lower() or q in isin.lower():
                results.append({"id": str(asset.id), "symbol": asset.symbol, "name": asset.name, "isin": isin})
        return results

    def _current_quantity(self, portfolio_id: int, asset_id: int) -> float:
        qty = 0.0
        for tx in self.transactions:
            if tx.portfolio_id != portfolio_id or tx.asset_id != asset_id:
                continue
            qty += tx.quantity if tx.side == "buy" else -tx.quantity
        return qty

    def _grouped_lots(self, portfolio_id: int) -> dict[int, dict[str, float]]:
        grouped: dict[int, dict[str, float]] = defaultdict(lambda: {"quantity": 0.0, "cost": 0.0})
        txs = [t for t in self.transactions if t.portfolio_id == portfolio_id]

        for tx in txs:
            lot = grouped[tx.asset_id]
            if tx.side == "buy":
                lot["quantity"] += tx.quantity
                lot["cost"] += tx.quantity * tx.price + tx.fees + tx.taxes
            else:
                if lot["quantity"] <= 0:
                    continue
                avg_cost = lot["cost"] / lot["quantity"]
                sold_qty = min(tx.quantity, lot["quantity"])
                lot["quantity"] -= sold_qty
                lot["cost"] -= avg_cost * sold_qty
                lot["cost"] = max(lot["cost"], 0.0)
        return grouped

    def _ensure_portfolio(self, portfolio_id: int) -> None:
        if portfolio_id not in self.portfolios:
            raise ValueError("Portfolio non trovato")
