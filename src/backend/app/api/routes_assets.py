from dataclasses import asdict as _asdict
from datetime import date

from fastapi import APIRouter, Depends, Query

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError, ProviderError
from ..finance_client import make_finance_client, QUOTE_TYPE_MAP, resolve_provider_symbol_candidates
from ..models import (
    AssetCoverageItem,
    AssetCreate,
    AssetDiscoverItem,
    AssetDiscoverResponse,
    AssetEnsureRequest,
    AssetEnsureResponse,
    AssetInfoPricePoint,
    AssetInfoResponse,
    AssetLatestQuoteResponse,
    AssetMetadataRead,
    AssetPricePoint,
    AssetProviderSymbolCreate,
    AssetProviderSymbolRead,
    AssetRead,
    BenchmarkItem,
    DataCoverageResponse,
    ErrorResponse,
    PortfolioTargetAllocationItem,
    PortfolioTargetAllocationUpsert,
    PortfolioTargetAssetPerformanceResponse,
    PortfolioTargetAssetIntradayPerformanceResponse,
    PortfolioTargetIntradayResponse,
    PortfolioTargetPerformanceResponse,
)
from ..repository import PortfolioRepository


def register_assets_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    settings: object,
    finance_client: object,
    justetf_client: object,
    historical_service: object,
    ensure_target_allocation_enabled: object,
) -> None:
    import threading

    def _resolve_asset_isin(asset_id: int) -> str | None:
        try:
            asset = repo.get_asset(asset_id)
            if asset.isin:
                return asset.isin.strip().upper()
        except ValueError:
            pass

        enrich = repo.get_etf_enrichment(asset_id)
        if enrich and enrich.get("isin"):
            return str(enrich["isin"]).strip().upper()

        meta = repo.get_asset_metadata(asset_id)
        if meta and meta.raw_info:
            raw = meta.raw_info if isinstance(meta.raw_info, dict) else {}
            raw_isin = raw.get("isin") or raw.get("ISIN")
            if isinstance(raw_isin, str) and raw_isin.strip():
                return raw_isin.strip().upper()

        try:
            pa = repo.get_asset_pricing_symbol(asset_id, provider=settings.finance_provider)
            symbol = pa.symbol.strip().upper()
            if len(symbol) == 12 and symbol[:2].isalpha():
                return symbol
        except ValueError:
            pass
        return None

    def _resolve_asset_symbol(asset_id: int) -> str | None:
        try:
            pricing_asset = repo.get_asset_pricing_symbol(asset_id, provider=settings.finance_provider)
            return pricing_asset.provider_symbol.strip().upper()
        except ValueError:
            pass
        try:
            asset = repo.get_asset(asset_id)
            return asset.symbol.strip().upper()
        except ValueError:
            return None

    def _pick_provider_symbol(
        *,
        symbol: str,
        provider_symbol: str | None = None,
        isin: str | None = None,
    ) -> str:
        normalized_symbol = symbol.strip().upper()
        explicit_provider_symbol = (provider_symbol or "").strip().upper()
        if explicit_provider_symbol and explicit_provider_symbol != normalized_symbol and "." in explicit_provider_symbol:
            return explicit_provider_symbol

        for candidate in resolve_provider_symbol_candidates(normalized_symbol, isin):
            candidate_base = candidate.split(".", 1)[0]
            if candidate_base == normalized_symbol:
                return candidate

        return explicit_provider_symbol or normalized_symbol

    def _repair_provider_symbol_from_isin(asset_id: int, symbol: str, provider: str, isin: str | None):
        for candidate in resolve_provider_symbol_candidates(symbol, isin):
            try:
                quote = finance_client.get_quote(candidate)
            except Exception:
                continue
            repo.upsert_asset_provider_symbol(
                AssetProviderSymbolCreate(
                    asset_id=asset_id,
                    provider=provider,
                    provider_symbol=candidate,
                )
            )
            return candidate, quote
        return None, None

    BENCHMARK_SYMBOLS = [
        {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust"},
    ]

    @router.post("/assets", response_model=AssetRead, responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def create_asset(payload: AssetCreate, _auth: AuthContext = Depends(require_auth_rate_limited)) -> AssetRead:
        try:
            return repo.create_asset(payload)
        except ValueError as exc:
            message = str(exc)
            if "gia esistente" in message.lower() or "duplicato" in message.lower() or "vincolo" in message.lower():
                raise AppError(code="conflict", message=message, status_code=409) from exc
            raise AppError(code="bad_request", message=message, status_code=400) from exc

    @router.get("/assets/search")
    def search_assets(q: str = Query(min_length=1), _auth: AuthContext = Depends(require_auth_rate_limited)) -> dict[str, list[dict[str, str]]]:
        return {"assets": repo.search_assets(q)}

    @router.get("/assets/{asset_id}/price-timeseries", response_model=list[AssetPricePoint])
    def get_asset_price_timeseries(
        asset_id: int,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> list[AssetPricePoint]:
        rows = repo.get_asset_price_timeseries(asset_id, start_date, end_date)
        return [AssetPricePoint(date=r["date"], close=r["close"]) for r in rows]

    @router.get("/benchmarks", response_model=list[BenchmarkItem])
    def get_benchmarks(_auth: AuthContext = Depends(require_auth_rate_limited)) -> list[BenchmarkItem]:
        result: list[BenchmarkItem] = []
        for bench in BENCHMARK_SYMBOLS:
            asset = repo.get_asset_by_symbol(bench["symbol"])
            if not asset:
                try:
                    symbol = bench["symbol"]
                    created_asset = repo.create_asset(
                        AssetCreate(
                            symbol=symbol,
                            name=bench["name"],
                            asset_type="etf",
                            exchange_code=None,
                            exchange_name=None,
                            quote_currency="EUR",
                            isin=None,
                            active=True,
                        )
                    )
                    provider = settings.finance_provider.strip().lower()
                    try:
                        repo.create_asset_provider_symbol(
                            AssetProviderSymbolCreate(
                                asset_id=created_asset.id,
                                provider=provider,
                                provider_symbol=symbol,
                            )
                        )
                    except ValueError:
                        pass
                    asset = {"id": created_asset.id, "symbol": created_asset.symbol, "name": created_asset.name or bench["name"]}
                except ValueError:
                    asset = repo.get_asset_by_symbol(bench["symbol"])
            if asset:
                result.append(BenchmarkItem(asset_id=asset["id"], symbol=asset["symbol"], name=asset["name"] or bench["name"]))
        return result

    @router.post(
        "/benchmarks/{asset_id}/backfill",
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def backfill_benchmark_prices(
        asset_id: int,
        portfolio_id: int = Query(...),
        days: int = Query(default=365, ge=30, le=2000),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> dict:
        try:
            historical_service.backfill_single_asset(
                asset_id=asset_id,
                portfolio_id=portfolio_id,
                days=days,
                user_id=_auth.user_id,
            )
            return {"status": "ok"}
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

    @router.get("/assets/discover", response_model=AssetDiscoverResponse)
    def discover_assets(q: str = Query(min_length=1), _auth: AuthContext = Depends(require_auth_rate_limited)) -> AssetDiscoverResponse:
        db_items = repo.search_assets(q)
        try:
            provider_items = finance_client.search_symbols(q)
        except Exception:
            provider_items = []

        results: list[AssetDiscoverItem] = []
        db_symbols = {str(item.get("symbol", "")).upper() for item in db_items}

        for item in db_items:
            symbol = str(item.get("symbol", ""))
            results.append(
                AssetDiscoverItem(
                    key=f'db:{item["id"]}',
                    source='db',
                    asset_id=int(item["id"]),
                    symbol=symbol,
                    name=item.get("name"),
                )
            )

        seen_provider_keys: set[str] = set()
        for item in provider_items:
            provider_symbol = (item.symbol or "").strip().upper()
            if not provider_symbol:
                continue
            exchange = (item.exchange or "").strip() or None
            dedupe_key = f"{provider_symbol}|{exchange or ''}"
            if dedupe_key in seen_provider_keys:
                continue
            seen_provider_keys.add(dedupe_key)
            if provider_symbol in db_symbols:
                continue
            results.append(
                AssetDiscoverItem(
                    key=f'provider:{provider_symbol}:{exchange or ""}',
                    source='provider',
                    asset_id=None,
                    symbol=provider_symbol,
                    name=item.instrument_name,
                    exchange=exchange,
                    provider=settings.finance_provider,
                    provider_symbol=provider_symbol,
                )
            )

        return AssetDiscoverResponse(items=results)

    @router.post(
        "/assets/ensure",
        response_model=AssetEnsureResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def ensure_asset(payload: AssetEnsureRequest, _auth: AuthContext = Depends(require_auth_rate_limited)) -> AssetEnsureResponse:
        if payload.source == "db":
            if payload.asset_id is None:
                raise AppError(code="bad_request", message="asset_id obbligatorio per source=db", status_code=400)
            try:
                asset = repo.get_asset(payload.asset_id)
            except ValueError as exc:
                raise AppError(code="not_found", message=str(exc), status_code=404) from exc
            return AssetEnsureResponse(asset_id=asset.id, symbol=asset.symbol, created=False)

        symbol = payload.symbol.strip().upper()
        if not symbol:
            raise AppError(code="bad_request", message="symbol obbligatorio", status_code=400)

        base_ccy = "EUR"
        if payload.portfolio_id is not None:
            try:
                base_ccy = repo.get_portfolio_base_currency(payload.portfolio_id, user_id=_auth.user_id)
            except ValueError as exc:
                raise AppError(code="not_found", message=str(exc), status_code=404) from exc

        created = False
        resolved_asset: AssetRead | None = None

        existing = repo.find_asset_by_symbol(symbol)
        if existing:
            try:
                resolved_asset = repo.get_asset(existing["id"])
            except ValueError as exc:
                raise AppError(code="not_found", message=str(exc), status_code=404) from exc
        else:
            detected_type = "stock"
            try:
                client = make_finance_client(settings)
                info = client.get_asset_info(symbol)
                if info.quote_type:
                    detected_type = QUOTE_TYPE_MAP.get(info.quote_type.upper(), "stock")
            except Exception:
                pass

            try:
                resolved_asset = repo.create_asset(
                    AssetCreate(
                        symbol=symbol,
                        name=(payload.name or symbol).strip() or symbol,
                        asset_type=detected_type,
                        exchange_code=None,
                        exchange_name=payload.exchange,
                        quote_currency=base_ccy,
                        isin=payload.isin.strip().upper() if payload.isin else None,
                        active=True,
                    )
                )
                created = True
            except ValueError:
                fallback = repo.find_asset_by_symbol(symbol)
                if fallback is None:
                    raise AppError(code="conflict", message="Asset esistente ma non risolvibile", status_code=409)
                try:
                    resolved_asset = repo.get_asset(fallback["id"])
                except ValueError as exc:
                    raise AppError(code="not_found", message=str(exc), status_code=404) from exc

        if resolved_asset is None:
            raise AppError(code="bad_request", message="Impossibile risolvere asset", status_code=400)

        provider_name = (payload.provider or settings.finance_provider).lower()
        resolved_provider_symbol = _pick_provider_symbol(
            symbol=symbol,
            provider_symbol=payload.provider_symbol,
            isin=payload.isin,
        )

        try:
            repo.upsert_asset_provider_symbol(
                AssetProviderSymbolCreate(
                    asset_id=resolved_asset.id,
                    provider=provider_name,
                    provider_symbol=resolved_provider_symbol,
                )
            )
        except ValueError as exc:
            message = str(exc).lower()
            if "esistente" not in message and "duplicato" not in message and "vincolo" not in message:
                raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

        return AssetEnsureResponse(asset_id=resolved_asset.id, symbol=resolved_asset.symbol, created=created)

    @router.get("/assets/{asset_id}", response_model=AssetRead, responses={404: {"model": ErrorResponse}})
    def get_asset(asset_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> AssetRead:
        try:
            return repo.get_asset(asset_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get("/assets/{asset_id}/info", response_model=AssetInfoResponse, responses={404: {"model": ErrorResponse}})
    def get_asset_info(asset_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> AssetInfoResponse:
        try:
            pricing_asset = repo.get_asset_pricing_symbol(asset_id, provider=settings.finance_provider)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc
        try:
            info = finance_client.get_asset_info(pricing_asset.provider_symbol)
        except Exception as exc:
            raise AppError(code="provider_error", message=f"Impossibile ottenere info: {exc}", status_code=502) from exc
        price_history: list[AssetInfoPricePoint] = []
        price_history_status = "available"
        try:
            start_5y = date.today().replace(year=date.today().year - 5).isoformat()
            bars = finance_client.get_daily_bars(
                pricing_asset.provider_symbol,
                start_date=start_5y,
                end_date=date.today().isoformat(),
            )
            price_history = [
                AssetInfoPricePoint(date=b.day.isoformat(), close=b.close)
                for i, b in enumerate(bars)
                if i % 5 == 0 or i == len(bars) - 1
            ]
            if not price_history:
                price_history_status = "empty"
        except Exception as exc:
            price_history_status = f"unavailable:{exc.__class__.__name__}"
        day_change_pct: float | None = None
        if info.current_price is not None and info.previous_close is not None and info.previous_close != 0:
            day_change_pct = round(((info.current_price / info.previous_close) - 1) * 100, 2)
        db_asset_type: str | None = None
        try:
            db_asset = repo.get_asset(asset_id)
            db_asset_type = db_asset.asset_type
        except ValueError:
            pass
        try:
            repo.upsert_asset_metadata(asset_id, _asdict(info))
        except Exception:
            pass

        return AssetInfoResponse(
            asset_id=asset_id,
            symbol=pricing_asset.symbol,
            name=info.name,
            asset_type=db_asset_type,
            quote_type=info.quote_type,
            sector=info.sector,
            industry=info.industry,
            country=info.country,
            market_cap=info.market_cap,
            trailing_pe=info.trailing_pe,
            forward_pe=info.forward_pe,
            dividend_yield=info.dividend_yield,
            beta=info.beta,
            fifty_two_week_high=info.fifty_two_week_high,
            fifty_two_week_low=info.fifty_two_week_low,
            avg_volume=info.avg_volume,
            currency=info.currency,
            current_price=info.current_price,
            previous_close=info.previous_close,
            day_change_pct=day_change_pct,
            description=info.description,
            price_history_5y=price_history,
            expense_ratio=info.expense_ratio,
            fund_family=info.fund_family,
            total_assets=info.total_assets,
            category=info.category,
            dividend_rate=info.dividend_rate,
            profit_margins=info.profit_margins,
            return_on_equity=info.return_on_equity,
            revenue_growth=info.revenue_growth,
            earnings_growth=info.earnings_growth,
            website=info.website,
            current_price_source=info.current_price_source,
            metadata_status=info.metadata_status,
            price_history_status=price_history_status,
            warnings=info.warnings,
        )

    @router.get("/assets/{asset_id}/metadata", response_model=AssetMetadataRead | None)
    def get_asset_metadata(asset_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)):
        """Get stored yFinance metadata for an asset."""
        return repo.get_asset_metadata(asset_id)

    @router.post("/assets/{asset_id}/metadata/refresh", response_model=AssetMetadataRead)
    def refresh_asset_metadata(asset_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)):
        """Fetch fresh metadata from yFinance and store it."""
        try:
            pricing_asset = repo.get_asset_pricing_symbol(asset_id, provider=settings.finance_provider)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc
        try:
            info = finance_client.get_asset_info(pricing_asset.provider_symbol)
        except Exception as exc:
            raise AppError(code="provider_error", message=f"Impossibile ottenere info: {exc}", status_code=502) from exc
        data = _asdict(info)
        repo.upsert_asset_metadata(asset_id, data)
        result = repo.get_asset_metadata(asset_id)
        if result is None:
            raise AppError(code="internal_error", message="Metadata non salvata", status_code=500)
        return result

    @router.post("/assets/metadata/refresh-all")
    def refresh_all_asset_metadata(
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ):
        """Refresh metadata for all active assets from yFinance. Runs synchronously."""
        assets = repo.get_assets_for_price_refresh(provider=settings.finance_provider)
        updated = 0
        errors = []
        for pa in assets:
            try:
                info = finance_client.get_asset_info(pa.provider_symbol)
                data = _asdict(info)
                repo.upsert_asset_metadata(pa.asset_id, data)
                updated += 1
            except Exception as exc:
                errors.append({"asset_id": pa.asset_id, "symbol": pa.symbol, "error": str(exc)})
        return {"updated": updated, "errors": errors}

    # --- ETF Enrichment (justETF) ---

    @router.get("/assets/{asset_id}/etf-enrichment")
    def get_etf_enrichment(asset_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)):
        """Get stored justETF enrichment data for an asset."""
        data = repo.get_etf_enrichment(asset_id)
        if data is None:
            raise AppError(code="not_found", message="Nessun dato ETF enrichment trovato", status_code=404)
        return data

    @router.post("/assets/{asset_id}/etf-enrichment/refresh")
    def refresh_etf_enrichment(asset_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)):
        """Fetch fresh ETF data from justETF and store it. Requires ISIN."""
        isin = _resolve_asset_isin(asset_id)
        if not isin:
            raise AppError(
                code="bad_request",
                message="ISIN non trovato per questo asset. Necessario per justETF lookup.",
                status_code=400,
            )

        try:
            data = justetf_client.fetch_profile(isin, symbol=_resolve_asset_symbol(asset_id))
        except ProviderError as exc:
            status_code = 502
            if exc.reason == "invalid_isin":
                status_code = 400
            elif exc.reason in {"disabled", "temporarily_blocked"}:
                status_code = 503
            raise AppError(
                code=exc.reason,
                message=exc.message,
                status_code=status_code,
                details={"provider": exc.provider, "operation": exc.operation, "symbol": exc.symbol},
            ) from exc

        repo.upsert_etf_enrichment(asset_id, isin, data)
        result = repo.get_etf_enrichment(asset_id)
        if result is None:
            raise AppError(code="internal_error", message="ETF enrichment non salvato", status_code=500)
        return result

    @router.post(
        "/asset-provider-symbols",
        response_model=AssetProviderSymbolRead,
        responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def create_asset_provider_symbol(
        payload: AssetProviderSymbolCreate,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> AssetProviderSymbolRead:
        try:
            return repo.create_asset_provider_symbol(payload)
        except ValueError as exc:
            message = str(exc)
            if "gia esistente" in message.lower() or "duplicato" in message.lower() or "vincolo" in message.lower():
                raise AppError(code="conflict", message=message, status_code=409) from exc
            raise AppError(code="bad_request", message=message, status_code=400) from exc

    @router.get(
        "/assets/{asset_id}/latest-quote",
        response_model=AssetLatestQuoteResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_asset_latest_quote(asset_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> AssetLatestQuoteResponse:
        try:
            pricing_asset = repo.get_asset_pricing_symbol(asset_id, provider=settings.finance_provider)
            used_provider_symbol = pricing_asset.provider_symbol
            try:
                quote = finance_client.get_quote(used_provider_symbol)
            except ProviderError as exc:
                asset = repo.get_asset(asset_id)
                repaired_symbol, repaired_quote = _repair_provider_symbol_from_isin(
                    asset_id=asset_id,
                    symbol=pricing_asset.symbol,
                    provider=settings.finance_provider,
                    isin=asset.isin,
                )
                if repaired_quote is None or repaired_symbol is None:
                    raise AppError(
                        code=exc.reason,
                        message=exc.message,
                        status_code=502,
                        details={"provider": exc.provider, "operation": exc.operation, "symbol": exc.symbol},
                    ) from exc
                used_provider_symbol = repaired_symbol
                quote = repaired_quote
            return AssetLatestQuoteResponse(
                asset_id=pricing_asset.asset_id,
                symbol=pricing_asset.symbol,
                provider=settings.finance_provider,
                provider_symbol=used_provider_symbol,
                price=quote.price,
                ts=quote.ts,
                quote_source=quote.source,
                is_realtime=quote.is_realtime,
                is_fallback=quote.is_fallback,
                stale=quote.stale,
                warning=quote.warning,
            )
        except ValueError as exc:
            message = str(exc)
            status = 404 if "asset non trovato" in message.lower() else 400
            code = "not_found" if status == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status) from exc

    @router.get("/symbols")
    def search_symbols(
        q: str = Query(min_length=1), _auth: AuthContext = Depends(require_auth_rate_limited)
    ) -> dict[str, list[dict[str, str | None]]]:
        from dataclasses import asdict
        symbols_list = finance_client.search_symbols(q)
        return {"symbols": [asdict(s) for s in symbols_list]}

    # --- Target Allocation ---

    @router.get(
        "/portfolios/{portfolio_id}/target-allocation",
        response_model=list[PortfolioTargetAllocationItem],
        responses={404: {"model": ErrorResponse}},
    )
    def get_target_allocation(portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> list[PortfolioTargetAllocationItem]:
        ensure_target_allocation_enabled()
        try:
            return repo.list_portfolio_target_allocations(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/target-performance",
        response_model=PortfolioTargetPerformanceResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_target_performance(
        portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)
    ) -> PortfolioTargetPerformanceResponse:
        ensure_target_allocation_enabled()
        try:
            return repo.get_portfolio_target_performance(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/target-performance/intraday",
        response_model=PortfolioTargetIntradayResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_target_performance_intraday(
        portfolio_id: int,
        date: date,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> PortfolioTargetIntradayResponse:
        ensure_target_allocation_enabled()
        try:
            return repo.get_portfolio_target_intraday_performance(portfolio_id, date, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/target-performance/assets",
        response_model=PortfolioTargetAssetPerformanceResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_target_asset_performance(
        portfolio_id: int,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> PortfolioTargetAssetPerformanceResponse:
        ensure_target_allocation_enabled()
        try:
            return repo.get_portfolio_target_asset_performance(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/target-performance/assets/intraday",
        response_model=PortfolioTargetAssetIntradayPerformanceResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_target_asset_intraday_performance(
        portfolio_id: int,
        date: date,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> PortfolioTargetAssetIntradayPerformanceResponse:
        ensure_target_allocation_enabled()
        try:
            return repo.get_portfolio_target_asset_intraday_performance(portfolio_id, date, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.post(
        "/portfolios/{portfolio_id}/target-allocation",
        response_model=PortfolioTargetAllocationItem,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def upsert_target_allocation(
        portfolio_id: int,
        payload: PortfolioTargetAllocationUpsert,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> PortfolioTargetAllocationItem:
        ensure_target_allocation_enabled()
        try:
            result = repo.upsert_portfolio_target_allocation(portfolio_id, payload, _auth.user_id)
            threading.Thread(
                target=historical_service.backfill_single_asset,
                kwargs={"asset_id": payload.asset_id, "portfolio_id": portfolio_id},
                daemon=True,
            ).start()
            return result
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.delete(
        "/portfolios/{portfolio_id}/target-allocation/{asset_id}",
        responses={404: {"model": ErrorResponse}},
    )
    def delete_target_allocation(portfolio_id: int, asset_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> dict[str, str]:
        ensure_target_allocation_enabled()
        try:
            repo.delete_portfolio_target_allocation(portfolio_id, asset_id, _auth.user_id)
            return {"status": "ok"}
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/data-coverage",
        response_model=DataCoverageResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_data_coverage(
        portfolio_id: int,
        days: int = Query(default=365, ge=1, le=2000),
        threshold_pct: float = Query(default=80, ge=0, le=100),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> DataCoverageResponse:
        ensure_target_allocation_enabled()
        try:
            rows = repo.get_price_coverage(portfolio_id, days=days, user_id=_auth.user_id)
            assets = [AssetCoverageItem(**r) for r in rows]
            sufficient = all(a.coverage_pct >= threshold_pct for a in assets) if assets else True
            return DataCoverageResponse(
                portfolio_id=portfolio_id,
                days=days,
                sufficient=sufficient,
                threshold_pct=threshold_pct,
                assets=assets,
            )
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc
