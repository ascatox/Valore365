"""Backfill automatico della cifratura dei campi all'avvio (TASK-57).

Con le chiavi configurate e DATA_BACKFILL_ON_STARTUP attivo (default), il
lifespan dell'app avvia ``FieldEncryptionBackfillRunner.start`` dopo
``init_field_crypto``: un thread daemon esegue ``app.crypto.backfill.backfill_all``
(cifra i valori ancora in chiaro, riempie blind index e source_sha256), così
l'avvio e il bind della porta non aspettano il database.

Concorrenza: ``pg_try_advisory_xact_lock(FIELD_ENCRYPTION_BACKFILL_LOCK_KEY)`` su
una connessione dedicata (``PgAdvisoryLock`` di market_data_sync, variante xact
per il pooler di Supabase in transaction mode). Lock non preso = un'altra
istanza (deploy sovrapposto) sta già lavorando: la run viene saltata.

Costo a regime: a dati già cifrati è una query "righe da fare" per tabella e
una riga di log. Tra un blocco e l'altro una pausa
(DATA_BACKFILL_BATCH_PAUSE_SECONDS) lascia spazio alle richieste nel pool.
Allo shutdown ``stop()`` ferma la run dopo il blocco corrente; il resto lo
riprende l'avvio successivo (il backfill è idempotente).

L'esito dell'ultima run di questo processo è in ``status()``
(GET /api/admin/field-encryption/backfill). Nessuna eccezione esce dal thread.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any, Callable

from ..crypto.backfill import backfill_all, describe_error
from .market_data_sync import PgAdvisoryLock

logger = logging.getLogger(__name__)

# Chiave del lock advisory (bigint arbitrario, distinto da MARKET_DATA_SYNC_LOCK_KEY).
FIELD_ENCRYPTION_BACKFILL_LOCK_KEY = 57_365_001


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class FieldEncryptionBackfillRunner:
    def __init__(
        self,
        engine,
        *,
        lock_factory: Callable[[Any], Any] | None = None,
        backfill: Callable[..., list] = backfill_all,
        thread_factory: Callable[..., Any] = threading.Thread,
    ) -> None:
        self.engine = engine
        self._lock_factory = lock_factory or (lambda eng: PgAdvisoryLock(eng, FIELD_ENCRYPTION_BACKFILL_LOCK_KEY))
        self._backfill = backfill
        self._thread_factory = thread_factory
        self._stop = threading.Event()
        self._thread: Any = None
        self._status_lock = threading.Lock()
        self._status: dict[str, Any] = {"status": "not_started"}

    # -- status ------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._status_lock:
            return {**self._status, "tables": dict(self._status.get("tables") or {})}

    def _set_status(self, **values: Any) -> None:
        with self._status_lock:
            self._status = values

    # -- lifecycle ---------------------------------------------------------

    def start(self, crypto, settings):
        """Start the background run; returns the thread, or None when it does not run."""
        try:
            if not bool(getattr(settings, "data_backfill_on_startup", True)):
                logger.info("field encryption backfill: disabled (DATA_BACKFILL_ON_STARTUP=false)")
                self._set_status(status="disabled", reason="DATA_BACKFILL_ON_STARTUP=false")
                return None
            if crypto is None or not crypto.enabled:
                logger.info("field encryption backfill: skipped (DATA_ENCRYPTION_KEYS not configured)")
                self._set_status(status="disabled", reason="DATA_ENCRYPTION_KEYS not configured")
                return None
            if self._thread is not None and self._thread.is_alive():
                logger.info("field encryption backfill: already running in this process")
                return None
            batch_size = max(1, int(getattr(settings, "data_backfill_batch_size", 500)))
            pause = max(0.0, float(getattr(settings, "data_backfill_batch_pause_seconds", 0.2)))
            self._stop.clear()
            thread = self._thread_factory(
                target=self.run,
                args=(crypto,),
                kwargs={"batch_size": batch_size, "batch_pause_seconds": pause},
                name="field-encryption-backfill",
                daemon=True,
            )
            thread.start()
            self._thread = thread
            return thread
        except Exception as exc:  # never break startup
            logger.error("field encryption backfill: could not start: %s", describe_error(exc))
            self._set_status(status="failed", error=describe_error(exc))
            return None

    def stop(self, timeout: float | None = 5.0) -> None:
        """Ask the run to stop after the current batch; wait at most ``timeout`` seconds."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            try:
                thread.join(timeout)
            except Exception:  # pragma: no cover - fake threads in tests
                pass

    # -- the run -----------------------------------------------------------

    def run(self, crypto, *, batch_size: int = 500, batch_pause_seconds: float = 0.0) -> dict[str, Any]:
        """Synchronous run under the advisory lock. Never raises; returns the status."""
        started_at = _utcnow_iso()
        t0 = time.monotonic()
        base = {"started_at": started_at, "finished_at": None, "tables": {}, "error": None}
        self._set_status(status="running", **base)
        try:
            lock = self._lock_factory(self.engine)
            if not lock.acquire():
                logger.info("field encryption backfill: skipped, another instance holds the lock")
                self._set_status(**{**base, "status": "skipped_locked", "finished_at": _utcnow_iso()})
                return self.status()
        except Exception as exc:
            logger.error("field encryption backfill: lock not available: %s", describe_error(exc))
            self._set_status(**{**base, "status": "failed", "finished_at": _utcnow_iso(), "error": describe_error(exc)})
            return self.status()

        logger.info("field encryption backfill: started (batch_size=%d)", batch_size)
        try:
            results = self._backfill(
                crypto,
                self.engine.begin,
                batch_size=batch_size,
                stop_event=self._stop,
                batch_pause_seconds=batch_pause_seconds,
                on_batch=lock.heartbeat,
                isolate_errors=True,
            )
            tables: dict[str, Any] = {}
            for r in results:
                tables[r.table] = {
                    "scanned": r.scanned,
                    "updated": r.updated,
                    "failed": len(r.failed),
                    "stopped": r.stopped,
                    "error": r.error,
                }
                if r.updated or r.failed or r.error:
                    logger.info(
                        "field encryption backfill: %s updated=%d failed=%d%s",
                        r.table, r.updated, len(r.failed), f" error={r.error}" if r.error else "",
                    )
            updated = sum(t["updated"] for t in tables.values())
            failed = sum(t["failed"] for t in tables.values())
            errors = [f"{name}: {t['error']}" for name, t in tables.items() if t["error"]]
            stopped = any(t["stopped"] for t in tables.values())
            if stopped:
                status = "stopped"
            elif failed or errors:
                status = "completed_with_errors"
            else:
                status = "completed"
            duration = time.monotonic() - t0
            log = logger.warning if (failed or errors) else logger.info
            log(
                "field encryption backfill: %s, rows updated=%d failed=%d table errors=%d in %.1fs",
                status, updated, failed, len(errors), duration,
            )
            self._set_status(
                status=status,
                started_at=started_at,
                finished_at=_utcnow_iso(),
                duration_seconds=round(duration, 3),
                rows_updated=updated,
                rows_failed=failed,
                tables=tables,
                error="; ".join(errors) or None,
            )
        except Exception as exc:
            logger.error("field encryption backfill: failed: %s", describe_error(exc))
            self._set_status(**{**base, "status": "failed", "finished_at": _utcnow_iso(), "error": describe_error(exc)})
        finally:
            try:
                lock.release()
            except Exception as exc:  # pragma: no cover - release already logs its own errors
                logger.warning("field encryption backfill: lock release failed: %s", describe_error(exc))
        return self.status()
