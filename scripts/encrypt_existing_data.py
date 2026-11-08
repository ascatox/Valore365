#!/usr/bin/env python3
"""
TASK-57: cifra i dati personali ancora in chiaro e riempie i blind index
(docs/field-encryption.md). Idempotente: le righe gia' cifrate vengono saltate.
Il backend fa lo stesso backfill da solo all'avvio (DATA_BACKFILL_ON_STARTUP):
lo script serve per esecuzioni manuali e per --rewrap-keys.

Uso (con le stesse variabili d'ambiente del backend: DATABASE_URL,
DATA_ENCRYPTION_KEYS, DATA_BLIND_INDEX_KEY, APP_ENV):

    python scripts/encrypt_existing_data.py --dry-run
    python scripts/encrypt_existing_data.py
    python scripts/encrypt_existing_data.py --table portfolios --batch-size 200
    python scripts/encrypt_existing_data.py --rewrap-keys [--dry-run]   # rotazione KEK

--rewrap-keys ricifra con la KEK attiva (la prima di DATA_ENCRYPTION_KEYS)
tutte le DEK ancora cifrate con una KEK precedente; i dati non cambiano.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = ROOT / "src" / "backend"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from app.config import get_settings  # noqa: E402
from app.crypto import build_field_crypto  # noqa: E402
from app.crypto.backfill import TARGETS, backfill_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Cifra i dati personali legacy e riempie i blind index (TASK-57)")
    parser.add_argument("--dry-run", action="store_true", help="Conta soltanto le righe da aggiornare, nessuna scrittura")
    parser.add_argument("--batch-size", type=int, default=500, help="Righe per transazione (default 500)")
    parser.add_argument(
        "--table",
        action="append",
        choices=[t.table for t in TARGETS],
        help="Limita il backfill a questa tabella (ripetibile)",
    )
    parser.add_argument(
        "--rewrap-keys",
        action="store_true",
        help="Rotazione KEK: ricifra le DEK con la KEK attiva invece di fare il backfill",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    crypto = build_field_crypto(get_settings())
    if not crypto.enabled and not args.dry_run:
        print("DATA_ENCRYPTION_KEYS non configurata: niente da cifrare (usa --dry-run per contare le righe).", file=sys.stderr)
        return 2
    if args.batch_size <= 0:
        print("--batch-size deve essere > 0", file=sys.stderr)
        return 2

    from app.db import engine

    prefix = "[dry-run] " if args.dry_run else ""
    if args.rewrap_keys:
        if not crypto.enabled:
            print("DATA_ENCRYPTION_KEYS non configurata.", file=sys.stderr)
            return 2
        result = crypto.rewrap_all(engine.begin, batch_size=args.batch_size, dry_run=args.dry_run)
        print(
            f"{prefix}DEK esaminate={result.scanned} ricifrate={result.rewrapped} "
            f"fallite={len(result.failed)} (KEK attiva: {crypto.keyring.active_kid})"
        )
        for user_id in result.failed[:50]:
            print(f"  fallita: {user_id}")
        return 1 if result.failed else 0

    results = backfill_all(
        crypto,
        engine.begin,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        tables=set(args.table) if args.table else None,
    )
    failed = 0
    for r in results:
        failed += len(r.failed)
        print(f"{prefix}{r.table}: esaminate={r.scanned} da aggiornare/aggiornate={r.updated} fallite={len(r.failed)}")
        for key in r.failed[:20]:
            print(f"  fallita: {key}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
