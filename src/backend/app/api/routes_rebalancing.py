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

        total_market_value = max(float(summary.market_value), 0.0)
        cash_input = float(payload.cash_to_allocate or 0.0)
        min_order = float(payload.min_order_value or 0.0)

        candidate_rows: list[dict] = []
        for target in target_alloc:
            current_alloc = allocation_by_asset.get(target.asset_id)
            pos = position_by_asset.get(target.asset_id)
            current_weight = float(current_alloc.weight_pct) if current_alloc else 0.0
            current_value = float(current_alloc.market_value) if current_alloc else 0.0
            current_qty = float(pos.quantity) if pos else 0.0
            drift = current_weight - float(target.weight_pct)
            quote_price = quote_by_asset.get(target.asset_id)
            quote_ccy = (quote_ccy_by_asset.get(target.asset_id) or summary.base_currency).upper()

            if payload.mode == "buy_only" and current_weight >= float(target.weight_pct):
                continue
            if payload.mode == "sell_only" and current_weight <= float(target.weight_pct):
                continue
            if payload.mode == "rebalance" and abs(drift) <= 0:
                continue

            side = "sell" if drift > 0 else "buy"
            if payload.mode == "buy_only":
                side = "buy"
            elif payload.mode == "sell_only":
                side = "sell"

            score = abs(drift) if payload.mode == "rebalance" else (
                max(float(target.weight_pct) - current_weight, 0.0) if side == "buy" else max(current_weight - float(target.weight_pct), 0.0)
            )
            if score <= 0:
                continue

            candidate_rows.append(
                {
                    "asset_id": target.asset_id,
                    "symbol": target.symbol,
                    "name": target.name,
                    "target_weight_pct": float(target.weight_pct),
                    "current_weight_pct": current_weight,
                    "drift_pct": round(drift, 2),
                    "current_quantity": current_qty,
                    "current_value": current_value,
                    "side": side,
                    "price": quote_price,
                    "trade_currency": quote_ccy,
                    "score": score,
                }
            )

        candidate_rows.sort(key=lambda r: r["score"], reverse=True)
        considered_rows = candidate_rows[: payload.max_transactions * 3]

        generated: list[RebalancePreviewItem] = []

        def _rounded_qty(raw_qty: float) -> float:
            if payload.rounding == "integer":
                qty = float(int(raw_qty))
                return qty if qty > 0 else 0.0
            return round(raw_qty, 8)

        def _append_item(row: dict, order_value: float) -> None:
            price = float(row["price"])
            qty = _rounded_qty(order_value / price if price > 0 else 0.0)
            gross_total = round(qty * price, 2)
            if qty <= 0 or gross_total <= 0:
                skipped.append(f"{row['symbol']}: quantità non valida dopo arrotondamento")
                return
            if min_order > 0 and gross_total < min_order:
                skipped.append(f"{row['symbol']}: ordine sotto soglia minima ({gross_total:.2f} < {min_order:.2f})")
                return
            if row["side"] == "sell" and qty > float(row["current_quantity"]) + 1e-9:
                skipped.append(f"{row['symbol']}: quantità in vendita superiore al posseduto")
                return

            generated.append(
                RebalancePreviewItem(
                    asset_id=int(row["asset_id"]),
                    symbol=str(row["symbol"]),
                    name=str(row["name"]),
                    target_weight_pct=round(float(row["target_weight_pct"]), 2),
                    current_weight_pct=round(float(row["current_weight_pct"]), 2),
                    drift_pct=round(float(row["drift_pct"]), 2),
                    current_quantity=round(float(row["current_quantity"]), 8),
                    side=row["side"],
                    trade_currency=str(row["trade_currency"]),
                    price=round(price, 6),
                    quantity=qty,
                    gross_total=gross_total,
                    tradable=True,
                    skip_reason=None,
                )
            )

        tradable_rows: list[dict] = []
        for row in considered_rows:
            if row["price"] is None or float(row["price"]) <= 0:
                skipped.append(f"{row['symbol']}: prezzo non disponibile")
                continue
            if str(row["trade_currency"]).upper() != summary.base_currency.upper():
                skipped.append(f"{row['symbol']}: valuta {row['trade_currency']} non supportata nel preview MVP")
                continue
            tradable_rows.append(row)

        if payload.mode == "buy_only":
            buy_rows = [r for r in tradable_rows if r["side"] == "buy"][: payload.max_transactions]
            score_sum = sum(float(r["score"]) for r in buy_rows)
            if score_sum <= 0:
                warnings.append("Nessun asset sotto target disponibile per acquisti")
            else:
                for row in buy_rows:
                    proportional_amount = cash_input * (float(row["score"]) / score_sum)
                    _append_item(row, proportional_amount)
        elif payload.mode == "sell_only":
            sell_rows = [r for r in tradable_rows if r["side"] == "sell"][: payload.max_transactions]
            for row in sell_rows:
                if total_market_value <= 0:
                    continue
                overweight_pct = max(float(row["drift_pct"]), 0.0)
                proposed_value = min(float(row["current_value"]), (overweight_pct / 100.0) * total_market_value)
                _append_item(row, proposed_value)
        else:  # rebalance
            rows = tradable_rows[: payload.max_transactions]
            for row in rows:
                if total_market_value <= 0:
                    continue
                drift_abs_pct = abs(float(row["drift_pct"]))
                proposed_value = min(float(row["current_value"]) if row["side"] == "sell" else 10**18, (drift_abs_pct / 100.0) * total_market_value)
                _append_item(row, proposed_value)

        generated.sort(key=lambda i: abs(i.drift_pct), reverse=True)
        generated = generated[: payload.max_transactions]

        proposed_buy_total = round(sum(i.gross_total for i in generated if i.side == "buy"), 2)
        proposed_sell_total = round(sum(i.gross_total for i in generated if i.side == "sell"), 2)
        estimated_cash_residual = round(cash_input + proposed_sell_total - proposed_buy_total, 2)

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
