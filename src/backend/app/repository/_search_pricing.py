from datetime import date

from sqlalchemy import text

from ._base import PricingAsset


class SearchPricingMixin:
    def get_asset_price_timeseries(
        self, asset_id: int, start_date: date | None = None, end_date: date | None = None,
    ) -> list[dict]:
        clauses = ["asset_id = :asset_id"]
        params: dict = {"asset_id": asset_id}
        if start_date:
            clauses.append("price_date >= :start_date")
            params["start_date"] = start_date
        if end_date:
            clauses.append("price_date <= :end_date")
            params["end_date"] = end_date
        where = " and ".join(clauses)
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(f"select price_date, close::float8 as close from price_bars_1d where {where} order by price_date asc"),
                params,
            ).mappings().all()
        return [{"date": str(r["price_date"]), "close": r["close"]} for r in rows]

    def get_asset_by_symbol(self, symbol: str) -> dict | None:
        base = symbol.split(".")[0].upper()
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    "select id, symbol, coalesce(name, '') as name from assets "
                    "where upper(symbol) = upper(:symbol) or upper(symbol) = :base or upper(symbol) like :pattern "
                    "order by id asc limit 1"
                ),
                {"symbol": symbol, "base": base, "pattern": f"{base}.%"},
            ).mappings().first()
        if not row:
            return None
        return {"id": int(row["id"]), "symbol": row["symbol"], "name": row["name"]}

    def search_assets(self, query: str) -> list[dict[str, str]]:
        q = f"%{query.lower().strip()}%"
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select id, symbol, coalesce(name, '') as name, coalesce(isin, '') as isin
                    from assets
                    where lower(symbol) like :q
                       or lower(coalesce(name, '')) like :q
                       or lower(coalesce(isin, '')) like :q
                    order by symbol asc
                    limit 25
                    """
                ),
                {"q": q},
            ).mappings().all()

        return [{"id": str(r["id"]), "symbol": r["symbol"], "name": r["name"], "isin": r["isin"]} for r in rows]

    def find_asset_by_symbol(self, symbol: str) -> dict | None:
        """Exact case-insensitive match on symbol, ignoring exchange_code. Returns first by id or None."""
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select id, symbol, coalesce(name, '') as name
                    from assets
                    where lower(symbol) = lower(:symbol)
                    order by id asc
                    limit 1
                    """
                ),
                {"symbol": symbol.strip()},
            ).mappings().first()
        if not row:
            return None
        return {"id": int(row["id"]), "symbol": row["symbol"], "name": row["name"]}

    def get_latest_close_price(self, asset_id: int) -> float | None:
        """Return the most recent close price for an asset, or None."""
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select close
                    from price_bars_1d
                    where asset_id = :asset_id
                    order by price_date desc
                    limit 1
                    """
                ),
                {"asset_id": asset_id},
            ).mappings().first()
        if not row:
            return None
        return float(row["close"])

    def get_assets_for_price_refresh(
        self,
        provider: str,
        portfolio_id: int | None = None,
        asset_scope: str = "target",
        user_id: str | None = None,
        prefer_symbol_then_isin: bool = False,
    ) -> list[PricingAsset]:
        provider_value = provider.strip().lower()
        scope = (asset_scope or "target").strip().lower()
        if scope not in {"target", "transactions", "all"}:
            raise ValueError("asset_scope non supportato")
        provider_symbol_expr = (
            "coalesce(nullif(a.symbol, ''), nullif(a.isin, ''), coalesce(aps.provider_symbol, a.symbol))"
            if prefer_symbol_then_isin
            else "coalesce(aps.provider_symbol, a.symbol)"
        )
        with self.engine.begin() as conn:
            if portfolio_id is None:
                rows = conn.execute(
                    text(
                        f"""
                        select a.id as asset_id,
                               a.symbol,
                               {provider_symbol_expr} as provider_symbol
                        from assets a
                        left join asset_provider_symbols aps
                          on aps.asset_id = a.id and aps.provider = :provider
                        where a.active = true
                        order by a.symbol asc
                        """
                    ),
                    {"provider": provider_value},
                ).mappings().all()
            else:
                if user_id and self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                    raise ValueError("Portfolio non trovato")
                if scope == "all":
                    rows = conn.execute(
                        text(
                            f"""
                            select a.id as asset_id,
                                   a.symbol,
                                   {provider_symbol_expr} as provider_symbol
                            from assets a
                            left join asset_provider_symbols aps
                              on aps.asset_id = a.id and aps.provider = :provider
                            where a.active = true
                            order by a.symbol asc
                            """
                        ),
                        {"provider": provider_value},
                    ).mappings().all()
                elif scope == "transactions":
                    rows = conn.execute(
                        text(
                            f"""
                            select distinct a.id as asset_id,
                                   a.symbol,
                                   {provider_symbol_expr} as provider_symbol
                            from transactions t
                            join assets a on a.id = t.asset_id
                            left join asset_provider_symbols aps
                              on aps.asset_id = a.id and aps.provider = :provider
                            where t.portfolio_id = :portfolio_id
                            order by a.symbol asc
                            """
                        ),
                        {"provider": provider_value, "portfolio_id": portfolio_id},
                    ).mappings().all()
                else:  # target
                    rows = conn.execute(
                        text(
                            f"""
                            select distinct a.id as asset_id,
                                   a.symbol,
                                   {provider_symbol_expr} as provider_symbol
                            from portfolio_target_allocations pta
                            join assets a on a.id = pta.asset_id
                            left join asset_provider_symbols aps
                              on aps.asset_id = a.id and aps.provider = :provider
                            where pta.portfolio_id = :portfolio_id and a.active = true
                            order by a.symbol asc
                            """
                        ),
                        {"provider": provider_value, "portfolio_id": portfolio_id},
                    ).mappings().all()

        return [
            PricingAsset(
                asset_id=int(r["asset_id"]),
                symbol=str(r["symbol"]),
                provider_symbol=str(r["provider_symbol"]),
            )
            for r in rows
        ]

    def save_price_tick(
        self,
        *,
        asset_id: int,
        provider: str,
        ts,
        last: float,
        bid: float | None,
        ask: float | None,
        volume: float | None,
        previous_close: float | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into price_ticks (asset_id, provider, ts, last, bid, ask, volume, previous_close)
                    values (:asset_id, :provider, :ts, :last, :bid, :ask, :volume, :previous_close)
                    """
                ),
                {
                    "asset_id": asset_id,
                    "provider": provider.strip().lower(),
                    "ts": ts,
                    "last": last,
                    "bid": bid,
                    "ask": ask,
                    "volume": volume,
                    "previous_close": previous_close,
                },
            )

    def batch_upsert_price_bars_1d(
        self,
        *,
        asset_id: int,
        provider: str,
        rows: list[dict],
    ) -> None:
        if not rows:
            return
        provider_value = provider.strip().lower()
        payload = [
            {
                "asset_id": asset_id,
                "provider": provider_value,
                "price_date": row["price_date"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            for row in rows
        ]
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into price_bars_1d (asset_id, provider, price_date, open, high, low, close, volume)
                    values (:asset_id, :provider, :price_date, :open, :high, :low, :close, :volume)
                    on conflict (asset_id, provider, price_date)
                    do update set
                      open = excluded.open,
                      high = excluded.high,
                      low = excluded.low,
                      close = excluded.close,
                      volume = excluded.volume
                    """
                ),
                payload,
            )

    def upsert_price_bar_1d(
        self,
        *,
        asset_id: int,
        provider: str,
        price_date: date,
        open_value: float,
        high_value: float,
        low_value: float,
        close_value: float,
        volume: float | None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into price_bars_1d (asset_id, provider, price_date, open, high, low, close, volume)
                    values (:asset_id, :provider, :price_date, :open, :high, :low, :close, :volume)
                    on conflict (asset_id, provider, price_date)
                    do update set
                      open = excluded.open,
                      high = excluded.high,
                      low = excluded.low,
                      close = excluded.close,
                      volume = excluded.volume
                    """
                ),
                {
                    "asset_id": asset_id,
                    "provider": provider.strip().lower(),
                    "price_date": price_date,
                    "open": open_value,
                    "high": high_value,
                    "low": low_value,
                    "close": close_value,
                    "volume": volume,
                },
            )

    def upsert_fx_rate_1d(
        self,
        *,
        from_ccy: str,
        to_ccy: str,
        provider: str,
        price_date: date,
        rate: float,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into fx_rates_1d (from_ccy, to_ccy, provider, price_date, rate)
                    values (:from_ccy, :to_ccy, :provider, :price_date, :rate)
                    on conflict (from_ccy, to_ccy, provider, price_date)
                    do update set rate = excluded.rate
                    """
                ),
                {
                    "from_ccy": from_ccy.upper(),
                    "to_ccy": to_ccy.upper(),
                    "provider": provider.strip().lower(),
                    "price_date": price_date,
                    "rate": rate,
                },
            )

    def batch_upsert_fx_rates_1d(
        self,
        *,
        from_ccy: str,
        to_ccy: str,
        provider: str,
        rows: list[dict],
    ) -> None:
        if not rows:
            return
        provider_value = provider.strip().lower()
        payload = [
            {
                "from_ccy": from_ccy.upper(),
                "to_ccy": to_ccy.upper(),
                "provider": provider_value,
                "price_date": row["price_date"],
                "rate": row["rate"],
            }
            for row in rows
        ]
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into fx_rates_1d (from_ccy, to_ccy, provider, price_date, rate)
                    values (:from_ccy, :to_ccy, :provider, :price_date, :rate)
                    on conflict (from_ccy, to_ccy, provider, price_date)
                    do update set rate = excluded.rate
                    """
                ),
                payload,
            )
