#!/usr/bin/env python3
"""
Backfill assets created with symbol=ISIN by resolving a provider ticker.

Default mode is dry-run.
Use --apply to persist changes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = ROOT / "src" / "backend"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from app.config import get_settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.finance_client import make_finance_client  # noqa: E402


ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")


def resolve_ticker(finance_client, isin: str) -> str | None:
    try:
        results = finance_client.search_symbols(isin)
    except Exception:
        return None
    for item in results:
        symbol = (item.symbol or "").strip().upper()
        if symbol and symbol != isin and not ISIN_RE.fullmatch(symbol):
            return symbol
    for item in results:
        symbol = (item.symbol or "").strip().upper()
        if symbol and symbol != isin:
            return symbol
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill ISIN symbols to provider tickers")
    parser.add_argument("--apply", action="store_true", help="Persist changes (default is dry-run)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of candidate assets (0 = no limit)")
    args = parser.parse_args()

    settings = get_settings()
    provider = settings.finance_provider.strip().lower()
    finance_client = make_finance_client(settings)

    sql = """
        select a.id, a.symbol, a.isin, a.exchange_code
        from assets a
        where a.active = true
          and a.isin is not null
          and (
            upper(a.symbol) = upper(a.isin)
            or upper(a.symbol) ~ '^[A-Z]{2}[A-Z0-9]{10}$'
          )
        order by a.id asc
    """
    if args.limit and args.limit > 0:
        sql += " limit :limit"

    with engine.begin() as conn:
        rows = conn.execute(text(sql), {"limit": args.limit} if args.limit and args.limit > 0 else {}).mappings().all()

    if not rows:
        print("No candidate assets found.")
        return 0

    print(f"Candidates: {len(rows)} (provider={provider})")
    updated_symbol = 0
    upserted_mapping = 0
    skipped = 0

    for row in rows:
        asset_id = int(row["id"])
        current_symbol = str(row["symbol"]).upper()
        isin = str(row["isin"]).upper()
        exchange_code = (row["exchange_code"] or "").upper() or None

        ticker = resolve_ticker(finance_client, isin)
        if not ticker:
            print(f"[SKIP] asset_id={asset_id} isin={isin} symbol={current_symbol} reason=no_ticker_resolved")
            skipped += 1
            continue

        print(f"[PLAN] asset_id={asset_id} isin={isin} symbol:{current_symbol} -> {ticker}")
        if not args.apply:
            continue

        with engine.begin() as conn:
            # Check provider_symbol collision on another asset.
            existing_ps = conn.execute(
                text(
                    """
                    select asset_id
                    from asset_provider_symbols
                    where provider = :provider and provider_symbol = :provider_symbol
                    """
                ),
                {"provider": provider, "provider_symbol": ticker},
            ).mappings().fetchone()
            if existing_ps and int(existing_ps["asset_id"]) != asset_id:
                print(
                    f"[SKIP] asset_id={asset_id} ticker={ticker} reason=provider_symbol_in_use_by_asset_{int(existing_ps['asset_id'])}"
                )
                skipped += 1
                continue

            conn.execute(
                text(
                    """
                    insert into asset_provider_symbols (asset_id, provider, provider_symbol)
                    values (:asset_id, :provider, :provider_symbol)
                    on conflict (asset_id, provider)
                    do update set provider_symbol = excluded.provider_symbol
                    """
                ),
                {"asset_id": asset_id, "provider": provider, "provider_symbol": ticker},
            )
            upserted_mapping += 1

            # Update assets.symbol only for ISIN-like symbol and if no direct conflict.
            if ISIN_RE.fullmatch(current_symbol):
                conflict = conn.execute(
                    text(
                        """
                        select id
                        from assets
                        where upper(symbol) = :symbol
                          and coalesce(exchange_code, '') = coalesce(:exchange_code, '')
                          and id <> :asset_id
                        limit 1
                        """
                    ),
                    {"symbol": ticker, "exchange_code": exchange_code, "asset_id": asset_id},
                ).mappings().fetchone()
                if conflict:
                    print(f"[SKIP] asset_id={asset_id} symbol_update_conflict_with_asset_{int(conflict['id'])}")
                    skipped += 1
                else:
                    conn.execute(
                        text("update assets set symbol = :symbol where id = :asset_id"),
                        {"symbol": ticker, "asset_id": asset_id},
                    )
                    updated_symbol += 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Done ({mode}). upserted_mapping={upserted_mapping} updated_symbol={updated_symbol} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

