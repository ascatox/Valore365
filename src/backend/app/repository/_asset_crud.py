from sqlalchemy import text

from ..sql import load_sql
from ..models import (
    AssetCreate,
    AssetMetadataRead,
    AssetProviderSymbolCreate,
    AssetProviderSymbolRead,
    AssetRead,
)
from ._base import PricingAsset


class AssetCrudMixin:
    def create_asset(self, payload: AssetCreate) -> AssetRead:
        symbol = payload.symbol.strip().upper()
        quote_currency = payload.quote_currency.strip().upper()
        exchange_code = payload.exchange_code.strip().upper() if payload.exchange_code else None
        isin = payload.isin.strip().upper() if payload.isin else None

        with self.engine.begin() as conn:
            try:
                row = conn.execute(
                    text(
                        """
                        insert into assets (symbol, name, asset_type, exchange_code, exchange_name, quote_currency, isin, active, supports_fractions)
                        values (:symbol, :name, :asset_type, :exchange_code, :exchange_name, :quote_currency, :isin, :active, :supports_fractions)
                        returning id
                        """
                    ),
                    {
                        "symbol": symbol,
                        "name": payload.name,
                        "asset_type": payload.asset_type,
                        "exchange_code": exchange_code,
                        "exchange_name": payload.exchange_name,
                        "quote_currency": quote_currency,
                        "isin": isin,
                        "active": payload.active,
                        "supports_fractions": payload.supports_fractions,
                    },
                ).fetchone()
            except Exception as exc:
                raise ValueError("Asset gia esistente o vincolo violato") from exc

        if row is None:
            raise ValueError("Impossibile creare asset")
        return self.get_asset(int(row.id))

    def update_asset_type(self, asset_id: int, asset_type: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("update assets set asset_type = :asset_type where id = :id"),
                {"asset_type": asset_type, "id": asset_id},
            )

    def get_portfolio_asset_ids(self, portfolio_id: int, user_id: str) -> list[int]:
        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")
            rows = conn.execute(
                text(
                    """
                    select distinct asset_id
                    from transactions
                    where portfolio_id = :pid and asset_id is not null
                    """
                ),
                {"pid": portfolio_id},
            ).fetchall()
            return [int(r[0]) for r in rows]

    def get_asset(self, asset_id: int) -> AssetRead:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select id, symbol, name, asset_type, exchange_code, exchange_name, quote_currency, isin, active, supports_fractions
                    from assets
                    where id = :id
                    """
                ),
                {"id": asset_id},
            ).mappings().fetchone()
        if row is None:
            raise ValueError("Asset non trovato")
        return AssetRead(
            id=int(row["id"]),
            symbol=str(row["symbol"]),
            name=row["name"],
            asset_type=str(row["asset_type"]),
            exchange_code=row["exchange_code"],
            exchange_name=row["exchange_name"],
            quote_currency=str(row["quote_currency"]),
            isin=row["isin"],
            active=bool(row["active"]),
            supports_fractions=bool(row["supports_fractions"]),
        )

    def get_asset_pricing_symbol(self, asset_id: int, provider: str = "yfinance") -> PricingAsset:
        provider_name = provider.strip().lower()
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select a.id as asset_id,
                           a.symbol,
                           coalesce(aps.provider_symbol, a.symbol) as provider_symbol
                    from assets a
                    left join asset_provider_symbols aps
                      on aps.asset_id = a.id
                     and aps.provider = :provider
                    where a.id = :asset_id
                    """
                ),
                {"asset_id": asset_id, "provider": provider_name},
            ).mappings().fetchone()
        if row is None:
            raise ValueError("Asset non trovato")
        return PricingAsset(
            asset_id=int(row["asset_id"]),
            symbol=str(row["symbol"]),
            provider_symbol=str(row["provider_symbol"]),
        )

    def create_asset_provider_symbol(self, payload: AssetProviderSymbolCreate) -> AssetProviderSymbolRead:
        provider = payload.provider.strip().lower()
        provider_symbol = payload.provider_symbol.strip().upper()
        with self.engine.begin() as conn:
            if not self._asset_exists(conn, payload.asset_id):
                raise ValueError("Asset non trovato")
            try:
                conn.execute(
                    text(
                        """
                        insert into asset_provider_symbols (asset_id, provider, provider_symbol)
                        values (:asset_id, :provider, :provider_symbol)
                        """
                    ),
                    {
                        "asset_id": payload.asset_id,
                        "provider": provider,
                        "provider_symbol": provider_symbol,
                    },
                )
            except Exception as exc:
                raise ValueError("Mapping provider gia esistente o vincolo violato") from exc
        return AssetProviderSymbolRead(
            asset_id=payload.asset_id,
            provider=provider,
            provider_symbol=provider_symbol,
        )

    # ------------------------------------------------------------------
    # Asset metadata (yFinance info)
    # ------------------------------------------------------------------

    def upsert_asset_metadata(self, asset_id: int, data: dict) -> None:
        """Insert or update asset metadata from yFinance info dict."""
        import json as _json
        raw_info = data.get("raw_info")
        raw_json = _json.dumps(raw_info) if raw_info else None

        with self.engine.begin() as conn:
            conn.execute(
                text(load_sql("upsert_asset_metadata")),
                {
                    "asset_id": asset_id,
                    "expense_ratio": data.get("expense_ratio"),
                    "fund_family": data.get("fund_family"),
                    "total_assets": data.get("total_assets"),
                    "category": data.get("category"),
                    "sector": data.get("sector"),
                    "industry": data.get("industry"),
                    "country": data.get("country"),
                    "market_cap": data.get("market_cap"),
                    "trailing_pe": data.get("trailing_pe"),
                    "forward_pe": data.get("forward_pe"),
                    "dividend_yield": data.get("dividend_yield"),
                    "dividend_rate": data.get("dividend_rate"),
                    "beta": data.get("beta"),
                    "fifty_two_week_high": data.get("fifty_two_week_high"),
                    "fifty_two_week_low": data.get("fifty_two_week_low"),
                    "avg_volume": data.get("avg_volume"),
                    "profit_margins": data.get("profit_margins"),
                    "return_on_equity": data.get("return_on_equity"),
                    "revenue_growth": data.get("revenue_growth"),
                    "earnings_growth": data.get("earnings_growth"),
                    "description": data.get("description"),
                    "website": data.get("website"),
                    "logo_url": data.get("logo_url"),
                    "raw_info": raw_json,
                },
            )

    def get_asset_metadata(self, asset_id: int) -> AssetMetadataRead | None:
        """Get stored metadata for an asset."""
        with self.engine.begin() as conn:
            row = conn.execute(
                text(load_sql("get_asset_metadata")),
                {"asset_id": asset_id},
            ).mappings().fetchone()

        if row is None:
            return None

        return AssetMetadataRead(
            asset_id=int(row["asset_id"]),
            expense_ratio=float(row["expense_ratio"]) if row["expense_ratio"] is not None else None,
            fund_family=row["fund_family"],
            total_assets=float(row["total_assets"]) if row["total_assets"] is not None else None,
            category=row["category"],
            sector=row["sector"],
            industry=row["industry"],
            country=row["country"],
            market_cap=float(row["market_cap"]) if row["market_cap"] is not None else None,
            trailing_pe=float(row["trailing_pe"]) if row["trailing_pe"] is not None else None,
            forward_pe=float(row["forward_pe"]) if row["forward_pe"] is not None else None,
            dividend_yield=float(row["dividend_yield"]) if row["dividend_yield"] is not None else None,
            dividend_rate=float(row["dividend_rate"]) if row["dividend_rate"] is not None else None,
            beta=float(row["beta"]) if row["beta"] is not None else None,
            fifty_two_week_high=float(row["fifty_two_week_high"]) if row["fifty_two_week_high"] is not None else None,
            fifty_two_week_low=float(row["fifty_two_week_low"]) if row["fifty_two_week_low"] is not None else None,
            avg_volume=float(row["avg_volume"]) if row["avg_volume"] is not None else None,
            profit_margins=float(row["profit_margins"]) if row["profit_margins"] is not None else None,
            return_on_equity=float(row["return_on_equity"]) if row["return_on_equity"] is not None else None,
            revenue_growth=float(row["revenue_growth"]) if row["revenue_growth"] is not None else None,
            earnings_growth=float(row["earnings_growth"]) if row["earnings_growth"] is not None else None,
            description=row["description"],
            website=row["website"],
            logo_url=row["logo_url"],
            raw_info=row["raw_info"],
            updated_at=row["updated_at"],
        )

    def get_asset_metadata_bulk(self, asset_ids: list[int]) -> dict[int, AssetMetadataRead]:
        """Get metadata for multiple assets at once."""
        if not asset_ids:
            return {}
        with self.engine.begin() as conn:
            rows = conn.execute(
                text("""
                    select asset_id, expense_ratio, fund_family, total_assets, category,
                           sector, industry, country, market_cap,
                           trailing_pe, forward_pe, dividend_yield, dividend_rate,
                           beta, fifty_two_week_high, fifty_two_week_low, avg_volume,
                           profit_margins, return_on_equity, revenue_growth, earnings_growth,
                           description, website, logo_url, updated_at
                    from asset_metadata
                    where asset_id = any(:ids)
                """),
                {"ids": asset_ids},
            ).mappings().all()

        result = {}
        for row in rows:
            aid = int(row["asset_id"])
            result[aid] = AssetMetadataRead(
                asset_id=aid,
                expense_ratio=float(row["expense_ratio"]) if row["expense_ratio"] is not None else None,
                fund_family=row["fund_family"],
                total_assets=float(row["total_assets"]) if row["total_assets"] is not None else None,
                category=row["category"],
                sector=row["sector"],
                industry=row["industry"],
                country=row["country"],
                market_cap=float(row["market_cap"]) if row["market_cap"] is not None else None,
                trailing_pe=float(row["trailing_pe"]) if row["trailing_pe"] is not None else None,
                forward_pe=float(row["forward_pe"]) if row["forward_pe"] is not None else None,
                dividend_yield=float(row["dividend_yield"]) if row["dividend_yield"] is not None else None,
                dividend_rate=float(row["dividend_rate"]) if row["dividend_rate"] is not None else None,
                beta=float(row["beta"]) if row["beta"] is not None else None,
                fifty_two_week_high=float(row["fifty_two_week_high"]) if row["fifty_two_week_high"] is not None else None,
                fifty_two_week_low=float(row["fifty_two_week_low"]) if row["fifty_two_week_low"] is not None else None,
                avg_volume=float(row["avg_volume"]) if row["avg_volume"] is not None else None,
                profit_margins=float(row["profit_margins"]) if row["profit_margins"] is not None else None,
                return_on_equity=float(row["return_on_equity"]) if row["return_on_equity"] is not None else None,
                revenue_growth=float(row["revenue_growth"]) if row["revenue_growth"] is not None else None,
                earnings_growth=float(row["earnings_growth"]) if row["earnings_growth"] is not None else None,
                description=row["description"],
                website=row["website"],
                logo_url=row["logo_url"],
                updated_at=row["updated_at"],
            )
        return result

    # --- ETF Enrichment (justETF) ---

    def upsert_etf_enrichment(self, asset_id: int, isin: str, data: dict) -> None:
        """Insert or update ETF enrichment data from justETF."""
        import json as _json
        with self.engine.begin() as conn:
            conn.execute(
                text(load_sql("upsert_etf_enrichment")),
                {
                    "asset_id": asset_id,
                    "isin": isin,
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "index_tracked": data.get("index_tracked"),
                    "investment_focus": data.get("investment_focus"),
                    "country_weights": _json.dumps(data.get("country_weights")) if data.get("country_weights") else None,
                    "sector_weights": _json.dumps(data.get("sector_weights")) if data.get("sector_weights") else None,
                    "top_holdings": _json.dumps(data.get("top_holdings")) if data.get("top_holdings") else None,
                    "holdings_date": data.get("holdings_date"),
                    "replication_method": data.get("replication_method"),
                    "distribution_policy": data.get("distribution_policy"),
                    "distribution_frequency": data.get("distribution_frequency"),
                    "fund_currency": data.get("fund_currency"),
                    "currency_hedged": data.get("currency_hedged"),
                    "domicile": data.get("domicile"),
                    "fund_provider": data.get("fund_provider"),
                    "fund_size_eur": data.get("fund_size_eur"),
                    "ter": data.get("ter"),
                    "volatility_1y": data.get("volatility_1y"),
                    "sustainability": data.get("sustainability"),
                    "inception_date": data.get("inception_date"),
                    "source": data.get("source", "justetf"),
                },
            )

    def get_etf_enrichment(self, asset_id: int) -> dict | None:
        """Get ETF enrichment data for a single asset."""
        with self.engine.begin() as conn:
            row = conn.execute(
                text(load_sql("get_etf_enrichment")),
                {"asset_id": asset_id},
            ).mappings().fetchone()

        if row is None:
            return None

        return {
            "asset_id": int(row["asset_id"]),
            "isin": row["isin"],
            "name": row["name"],
            "description": row["description"],
            "index_tracked": row["index_tracked"],
            "investment_focus": row["investment_focus"],
            "country_weights": row["country_weights"],
            "sector_weights": row["sector_weights"],
            "top_holdings": row["top_holdings"],
            "holdings_date": row["holdings_date"],
            "replication_method": row["replication_method"],
            "distribution_policy": row["distribution_policy"],
            "distribution_frequency": row["distribution_frequency"],
            "fund_currency": row["fund_currency"],
            "currency_hedged": row["currency_hedged"],
            "domicile": row["domicile"],
            "fund_provider": row["fund_provider"],
            "fund_size_eur": float(row["fund_size_eur"]) if row["fund_size_eur"] is not None else None,
            "ter": float(row["ter"]) if row["ter"] is not None else None,
            "volatility_1y": float(row["volatility_1y"]) if row["volatility_1y"] is not None else None,
            "sustainability": row["sustainability"],
            "inception_date": row["inception_date"],
            "source": row["source"],
            "fetched_at": row["fetched_at"].isoformat() if row["fetched_at"] else None,
        }

    def get_etf_enrichment_bulk(self, asset_ids: list[int]) -> dict[int, dict]:
        """Get ETF enrichment data for multiple assets."""
        if not asset_ids:
            return {}
        with self.engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT asset_id, isin, name, description, index_tracked, investment_focus,
                           country_weights, sector_weights, top_holdings, holdings_date,
                           replication_method, distribution_policy, distribution_frequency,
                           fund_currency, currency_hedged, domicile, fund_provider,
                           fund_size_eur, ter, volatility_1y, sustainability, inception_date,
                           source, fetched_at
                    FROM etf_enrichment
                    WHERE asset_id = ANY(:ids)
                """),
                {"ids": asset_ids},
            ).mappings().all()

        result = {}
        for row in rows:
            aid = int(row["asset_id"])
            result[aid] = {
                "asset_id": aid,
                "isin": row["isin"],
                "name": row["name"],
                "description": row["description"],
                "index_tracked": row["index_tracked"],
                "investment_focus": row["investment_focus"],
                "country_weights": row["country_weights"],
                "sector_weights": row["sector_weights"],
                "top_holdings": row["top_holdings"],
                "holdings_date": row["holdings_date"],
                "replication_method": row["replication_method"],
                "distribution_policy": row["distribution_policy"],
                "distribution_frequency": row["distribution_frequency"],
                "fund_currency": row["fund_currency"],
                "currency_hedged": row["currency_hedged"],
                "domicile": row["domicile"],
                "fund_provider": row["fund_provider"],
                "fund_size_eur": float(row["fund_size_eur"]) if row["fund_size_eur"] is not None else None,
                "ter": float(row["ter"]) if row["ter"] is not None else None,
                "volatility_1y": float(row["volatility_1y"]) if row["volatility_1y"] is not None else None,
                "sustainability": row["sustainability"],
                "inception_date": row["inception_date"],
                "source": row["source"],
                "fetched_at": row["fetched_at"].isoformat() if row["fetched_at"] else None,
            }
        return result

    def get_stale_etf_enrichments(self, max_age_days: int = 30) -> list[tuple[int, str]]:
        """Get asset_id + ISIN pairs where enrichment data is stale."""
        with self.engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT e.asset_id, e.isin
                    FROM etf_enrichment e
                    WHERE e.fetched_at < now() - make_interval(days => :max_age)
                    ORDER BY e.fetched_at ASC
                """),
                {"max_age": max_age_days},
            ).fetchall()
        return [(int(r[0]), str(r[1])) for r in rows]
