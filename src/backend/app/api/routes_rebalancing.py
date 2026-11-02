import threading

from fastapi import APIRouter, Depends

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError
from ..models import (
    ErrorResponse,
    RebalanceCommitCreatedItem,
    RebalanceCommitRequest,
    RebalanceCommitResponse,
    RebalancePreviewItem,
    RebalancePreviewRequest,
    RebalancePreviewResponse,
    RebalancePreviewSummary,
    TransactionCreate,
)
from ..repository import PortfolioRepository
from ..services.rebalance import RebalanceHolding, compute_rebalance_plan


def register_rebalancing_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    settings: object,
    finance_client: object,
    historical_service: object,
    ensure_target_allocation_enabled: object,
) -> None:

    @router.post(
        "/portfolios/{portfolio_id}/rebalance/preview",
        response_model=RebalancePreviewResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def rebalance_preview(
        portfolio_id: int,
        payload: RebalancePreviewRequest,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> RebalancePreviewResponse:
        ensure_target_allocation_enabled()
        try:
            target_alloc = repo.list_portfolio_target_allocations(portfolio_id, _auth.user_id)
            summary = repo.get_summary(portfolio_id, _auth.user_id)
            allocation = repo.get_allocation(portfolio_id, _auth.user_id)
            positions = repo.get_positions(portfolio_id, _auth.user_id)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

        if not target_alloc:
            return RebalancePreviewResponse(
                portfolio_id=portfolio_id,
                base_currency=summary.base_currency,
                mode=payload.mode,
                trade_at=payload.trade_at,
                summary=RebalancePreviewSummary(
                    proposed_buy_total=0.0,
                    proposed_sell_total=0.0,
                    cash_input=round(float(payload.cash_to_allocate or 0), 2),
                    estimated_cash_residual=round(float(payload.cash_to_allocate or 0), 2),
                    generated_count=0,
                    skipped_count=0,
                ),
                items=[],
                warnings=["Nessuna allocazione target configurata"],
            )

        if payload.mode == "buy_only" and (payload.cash_to_allocate is None or payload.cash_to_allocate <= 0):
            raise AppError(code="bad_request", message="cash_to_allocate > 0 obbligatorio in modalità buy_only", status_code=400)

        allocation_by_asset = {item.asset_id: item for item in allocation}
        position_by_asset = {item.asset_id: item for item in positions}
        quote_ccy_by_asset = repo.get_quote_currencies_for_assets([t.asset_id for t in target_alloc])

        quote_by_asset: dict[int, float] = {}
        skipped: list[str] = []
        warnings: list[str] = []

        for target in target_alloc:
            aid = target.asset_id
            quote_ccy = (quote_ccy_by_asset.get(aid) or summary.base_currency).upper()
            if quote_ccy != summary.base_currency.upper():
                skipped.append(f"{target.symbol}: valuta {quote_ccy} diversa da {summary.base_currency} (preview MVP)")
                continue

            try:
                if payload.use_latest_prices:
                    pricing_asset = repo.get_asset_pricing_symbol(aid, provider=settings.finance_provider)
                    quote = finance_client.get_quote(pricing_asset.provider_symbol)
                    quote_by_asset[aid] = float(quote.price)
                else:
                    pos = position_by_asset.get(aid)
                    if pos and pos.market_price > 0:
                        quote_by_asset[aid] = float(pos.market_price)
                    else:
                        skipped.append(f"{target.symbol}: prezzo non disponibile")
            except Exception as exc:  # noqa: BLE001 - preview should degrade gracefully
                skipped.append(f"{target.symbol}: prezzo non disponibile ({exc})")

        cash_input = float(payload.cash_to_allocate or 0.0)
        min_order = float(payload.min_order_value or 0.0)
        base_ccy = summary.base_currency.upper()

        # Shared, order-independent algorithm (app.services.rebalance). The
        # preview keeps its historical semantics: weights on the invested
        # value of all holdings (cash excluded), no tolerance band, buy_only
        # deploys all of cash_to_allocate. Buys are now funded by
        # cash_to_allocate + sell proceeds (scaled down if short).
        target_by_asset = {t.asset_id: t for t in target_alloc}
        holdings: list[RebalanceHolding] = []
        for item in allocation:
            if item.asset_id in target_by_asset:
                continue
            holdings.append(RebalanceHolding(key=item.asset_id, symbol=item.symbol, current_value=float(item.market_value)))
        for target in target_alloc:
            aid = target.asset_id
            current_alloc = allocation_by_asset.get(aid)
            quote_ccy = (quote_ccy_by_asset.get(aid) or summary.base_currency).upper()
            price = quote_by_asset.get(aid)
            holdings.append(
                RebalanceHolding(
                    key=aid,
                    symbol=target.symbol,
                    current_value=float(current_alloc.market_value) if current_alloc else 0.0,
                    target_weight_pct=float(target.weight_pct),
                    tradable=price is not None and price > 0 and quote_ccy == base_ccy,
                )
            )

        plan = compute_rebalance_plan(
            holdings,
            portfolio_cash=0.0,
            extra_cash=cash_input,
            mode=payload.mode,
            tolerance_pp=0.0,
            include_cash_in_base=False,
            include_untargeted_in_base=True,
            max_orders=payload.max_transactions,
            buy_only_deploy_all_cash=True,
        )
        if plan.buys_scaled:
            warnings.append("Liquidità insufficiente: acquisti ridotti in proporzione")

        generated: list[RebalancePreviewItem] = []

        def _rounded_qty(raw_qty: float) -> float:
            if payload.rounding == "integer":
                qty = float(int(raw_qty))
                return qty if qty > 0 else 0.0
            return round(raw_qty, 8)

        for order in plan.orders:
            target = target_by_asset[order.key]
            pos = position_by_asset.get(order.key)
            current_qty = float(pos.quantity) if pos else 0.0
            price = float(quote_by_asset[order.key])
            qty = _rounded_qty(order.amount / price if price > 0 else 0.0)
            gross_total = round(qty * price, 2)
            if qty <= 0 or gross_total <= 0:
                skipped.append(f"{order.symbol}: quantità non valida dopo arrotondamento")
                continue
            if min_order > 0 and gross_total < min_order:
                skipped.append(f"{order.symbol}: ordine sotto soglia minima ({gross_total:.2f} < {min_order:.2f})")
                continue
            if order.side == "sell" and qty > current_qty + 1e-9:
                skipped.append(f"{order.symbol}: quantità in vendita superiore al posseduto")
                continue
            generated.append(
                RebalancePreviewItem(
                    asset_id=int(order.key),
                    symbol=str(order.symbol),
                    name=str(target.name),
                    target_weight_pct=round(order.target_weight_pct, 2),
                    current_weight_pct=round(order.current_weight_pct, 2),
                    drift_pct=round(order.drift_pct, 2),
                    current_quantity=round(current_qty, 8),
                    side=order.side,
                    trade_currency=base_ccy,
                    price=round(price, 6),
                    quantity=qty,
                    gross_total=gross_total,
                    tradable=True,
                    skip_reason=None,
                )
            )

        if payload.mode == "buy_only" and not any(o.side == "buy" for o in plan.orders):
            warnings.append("Nessun asset sotto target disponibile per acquisti")

        generated.sort(key=lambda i: abs(i.drift_pct), reverse=True)
        generated = generated[: payload.max_transactions]

        proposed_buy_total = round(sum(i.gross_total for i in generated if i.side == "buy"), 2)
        proposed_sell_total = round(sum(i.gross_total for i in generated if i.side == "sell"), 2)
        estimated_cash_residual = round(cash_input + proposed_sell_total - proposed_buy_total, 2)
        if estimated_cash_residual < 0:
            warnings.append("Liquidità residua negativa dopo l'arrotondamento delle quantità")

        if skipped:
            warnings.append(f"Asset/proposte saltate: {len(skipped)}")

        return RebalancePreviewResponse(
            portfolio_id=portfolio_id,
            base_currency=summary.base_currency,
            mode=payload.mode,
            trade_at=payload.trade_at,
            summary=RebalancePreviewSummary(
                proposed_buy_total=proposed_buy_total,
                proposed_sell_total=proposed_sell_total,
                cash_input=round(cash_input, 2),
                estimated_cash_residual=estimated_cash_residual,
                generated_count=len(generated),
                skipped_count=len(skipped),
            ),
            items=generated,
            warnings=warnings + skipped[:20],
        )

    @router.post(
        "/portfolios/{portfolio_id}/rebalance/commit",
        response_model=RebalanceCommitResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def rebalance_commit(
        portfolio_id: int,
        payload: RebalanceCommitRequest,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> RebalanceCommitResponse:
        ensure_target_allocation_enabled()
        try:
            portfolio_summary = repo.get_summary(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

        created_items: list[RebalanceCommitCreatedItem] = []
        errors: list[str] = []
        touched_assets: set[int] = set()

        for idx, item in enumerate(payload.items, start=1):
            try:
                tx = repo.create_transaction(
                    TransactionCreate(
                        portfolio_id=portfolio_id,
                        asset_id=item.asset_id,
                        side=item.side,
                        trade_at=payload.trade_at,
                        quantity=item.quantity,
                        price=item.price,
                        fees=item.fees,
                        taxes=item.taxes,
                        trade_currency=portfolio_summary.base_currency,
                        notes=item.notes,
                    ),
                    _auth.user_id,
                )
                created_items.append(
                    RebalanceCommitCreatedItem(
                        transaction_id=tx.id,
                        asset_id=tx.asset_id,
                        side=tx.side,
                        quantity=tx.quantity,
                        price=tx.price,
                    )
                )
                touched_assets.add(tx.asset_id)
            except ValueError as exc:
                errors.append(f"Riga {idx} asset_id={item.asset_id}: {exc}")

        for asset_id in touched_assets:
            threading.Thread(
                target=historical_service.backfill_single_asset,
                kwargs={"asset_id": asset_id, "portfolio_id": portfolio_id},
                daemon=True,
            ).start()

        return RebalanceCommitResponse(
            portfolio_id=portfolio_id,
            requested=len(payload.items),
            created=len(created_items),
            failed=len(payload.items) - len(created_items),
            items=created_items,
            errors=errors,
        )
