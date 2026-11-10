"""Orchestratore della seduta del Tribunale (TASK-65).

Mette in sequenza fascicolo (``case_file``), voci (``personas``), chiamata strutturata
(``copilot.structured``) e verificatore (``verifier``) ed espone la seduta come stream SSE.

Contratto: ``docs/tribunale/api-contracts.md`` §3 (controlli prima dello stream ed errori),
§8 (fasi, voci valide, timeout, concorrenza, chiave e limite, seduta salvata) e §9 (eventi
SSE); firme in ``docs/tribunale/architecture.md`` §2.1. TASK-66 sostituisce solo
``_default_store``.

Log (``app.services.tribunal``): solo conteggi, durate e codici di scarto; mai fascicolo,
testi, prompt o messaggi delle eccezioni del provider.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from ...copilot.config import CopilotConfig, _decrypt_api_key, resolve_copilot_config
from ...copilot.streaming import HEARTBEAT_INTERVAL_S
from ...copilot.structured import (
    STRUCTURED_OUTPUT_PROVIDERS,
    StructuredOutputError,
    call_structured,
)
from ...errors import AppError
from ..doctor_policy.errors import error_details
from ..doctor_policy.scope import build_scope
from .case_file import CONTRACT_VERSION, MIN_CITABLE_FACTS, build_case_file, compute_case_file_hash
from .personas import (
    PROMPT_VERSION,
    VOICE_IDS,
    VOICES,
    build_opening_request,
    build_rebuttal_request,
    build_synthesis_request,
)
from .verifier import verify_opening, verify_rebuttals, verify_synthesis

logger = logging.getLogger("app.services.tribunal")

CALL_TIMEOUT_S = 45
SESSION_TIMEOUT_S = 180
DEFAULT_DAILY_LIMIT = 3
KeySource = Literal["user", "server"]

_HEARTBEAT = ": keepalive\n\n"
_ROME = ZoneInfo("Europe/Rome")
_VOICE_ERROR_CODES = ("timeout", "schema_mismatch", "provider_error", "unsupported_provider")

# Testi italiani per l'utente (ui-spec.md §4.1; too_few_voices come api-contracts §9.3.10).
_ERROR_MESSAGES = {
    "timeout": "La seduta ha impiegato troppo tempo ed è stata interrotta.",
    "too_few_voices": (
        "Meno di due voci hanno prodotto argomenti verificabili: la seduta è stata interrotta. "
        "Riprova tra poco."
    ),
    "synthesis_failed": "La sintesi non è riuscita. Gli argomenti delle voci restano visibili.",
    "internal_error": "Errore imprevisto durante la seduta.",
}
_ERROR_RETRYABLE = {"timeout": True, "too_few_voices": True, "synthesis_failed": True, "internal_error": False}
_VOICE_ERROR_MESSAGES = {
    "timeout": "{name} non ha risposto in tempo: la seduta prosegue con le altre voci.",
    "schema_mismatch": "{name} ha risposto in un formato non valido: la seduta prosegue con le altre voci.",
    "provider_error": (
        "{name} non è disponibile per un errore del servizio AI: la seduta prosegue con le altre voci."
    ),
    "unsupported_provider": (
        "{name} non è disponibile per un errore del servizio AI: la seduta prosegue con le altre voci."
    ),
}
_STATUS_MESSAGES = {
    "copilot_not_configured": (
        "Il Tribunale usa il Copilot, che non è ancora configurato. "
        "Aggiungi una chiave API in Impostazioni → Copilot."
    ),
    "provider_not_supported": (
        "Il modello configurato non supporta le risposte strutturate richieste dal Tribunale. "
        "In Impostazioni → Copilot scegli OpenAI, Anthropic, Gemini oppure OpenRouter."
    ),
    "daily_limit_reached": (
        "Hai usato tutte le sedute di oggi disponibili con la chiave del server. "
        "Con una tua chiave API, in Impostazioni → Copilot, non ci sono limiti giornalieri."
    ),
}


# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TribunalConfig:
    config: CopilotConfig
    key_source: KeySource


def resolve_tribunal_config(settings: Any, repo: Any, user_id: str) -> TribunalConfig | None:
    """Configurazione Copilot dell'utente e chi paga la chiamata (api-contracts §8.6).

    ``key_source = "user"`` se l'utente ha ``copilot_provider`` e una chiave cifrata che si
    decifra (primo ramo di ``resolve_copilot_config``), altrimenti ``"server"``.
    """
    user_settings = repo.get_user_settings(user_id)
    user_provider = getattr(user_settings, "copilot_provider", "") or ""
    user_model = getattr(user_settings, "copilot_model", "") or ""
    user_key_enc = repo.get_user_copilot_api_key_enc(user_id) or ""
    config = resolve_copilot_config(
        settings, user_provider=user_provider, user_model=user_model, user_api_key_enc=user_key_enc,
    )
    if config is None:
        return None
    user_branch = bool(user_provider and user_key_enc and _decrypt_api_key(user_key_enc, settings))
    return TribunalConfig(config=config, key_source="user" if user_branch else "server")


# ---------------------------------------------------------------------------
# SSE
# ---------------------------------------------------------------------------

def sse_event(event_type: str, content: dict[str, Any]) -> str:
    """Evento SSE su una riga (api-contracts §9.1): ``content`` è sempre un oggetto."""
    return f"data: {json.dumps({'type': event_type, 'content': content}, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class SessionStore(Protocol):
    def get_latest(self, user_id: str, scope_fingerprint: str) -> dict[str, Any] | None: ...

    def save(self, user_id: str, portfolio_ids: list[int], session: dict[str, Any], *,
             key_source: KeySource) -> None: ...

    def count_today(self, user_id: str, *, now: datetime | None = None) -> int: ...


class NullSessionStore:
    """Store nullo finché TASK-66 non è chiuso: niente seduta salvata, uso sempre 0."""

    def get_latest(self, user_id: str, scope_fingerprint: str) -> dict[str, Any] | None:
        return None

    def save(self, user_id: str, portfolio_ids: list[int], session: dict[str, Any], *,
             key_source: KeySource) -> None:
        return None

    def count_today(self, user_id: str, *, now: datetime | None = None) -> int:
        return 0


def _default_store(repo: Any) -> SessionStore:
    return NullSessionStore()


StructuredCall = Callable[..., dict[str, Any]]


# ---------------------------------------------------------------------------
# Lock: una seduta in corso per utente, per processo (api-contracts §8.5)
# ---------------------------------------------------------------------------

class _SessionLocks:
    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._active: set[str] = set()

    def acquire(self, user_id: str) -> bool:
        with self._mutex:
            if user_id in self._active:
                return False
            self._active.add(user_id)
            return True

    def release(self, user_id: str) -> None:
        with self._mutex:
            self._active.discard(user_id)

    def active(self, user_id: str) -> bool:
        with self._mutex:
            return user_id in self._active


_LOCKS = _SessionLocks()


class _LockedStream:
    """Iteratore SSE che libera il lock dell'utente alla fine, alla chiusura o se viene
    abbandonato senza essere mai letto (un generatore mai avviato non esegue ``finally``)."""

    def __init__(self, inner: Iterator[str], release: Callable[[], None]) -> None:
        self._inner = inner
        self._release_fn: Callable[[], None] | None = release

    def _release(self) -> None:
        fn, self._release_fn = self._release_fn, None
        if fn is not None:
            fn()

    def __iter__(self) -> "_LockedStream":
        return self

    def __next__(self) -> str:
        try:
            return next(self._inner)
        except BaseException:
            self._release()
            raise

    def close(self) -> None:
        try:
            close = getattr(self._inner, "close", None)
            if callable(close):
                close()
        finally:
            self._release()

    def __del__(self) -> None:  # pragma: no cover - dipende dal garbage collector
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Errori prima dello stream (api-contracts §3.4)
# ---------------------------------------------------------------------------

class TribunalError(AppError):
    """AppError con header HTTP opzionali (``Retry-After`` del limite giornaliero)."""

    def __init__(self, code: str, message: str, status_code: int, *, retryable: bool = False,
                 extra: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> None:
        details = error_details(retryable=retryable)
        details.update(extra or {})
        super().__init__(code=code, message=message, status_code=status_code, details=details)
        self.headers = dict(headers or {})


class _SessionTimeout(Exception):
    pass


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_rome_midnight(now: datetime) -> datetime:
    """Prossima mezzanotte Europe/Rome, in UTC."""
    local = now.astimezone(_ROME)
    tomorrow = (local + timedelta(days=1)).date()
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=_ROME).astimezone(UTC)


# ---------------------------------------------------------------------------
# Orchestratore
# ---------------------------------------------------------------------------

@dataclass
class _VoiceOutcome:
    voice: str | None
    result: Any = None          # VerificationResult / SynthesisVerification
    error_code: str | None = None
    ms: int = 0


class TribunalOrchestrator:
    def __init__(
        self,
        repo: Any,
        settings: Any,
        *,
        store: SessionStore | None = None,
        llm_call: StructuredCall | None = None,
        service_getter: Callable[[], Any] | None = None,
        finance_client: Any = None,
        justetf_client: Any = None,
        case_file_builder: Callable[..., dict[str, Any]] | None = None,
        clock: Callable[[], datetime] | None = None,
        session_timeout_s: float = SESSION_TIMEOUT_S,
        heartbeat_interval_s: float = HEARTBEAT_INTERVAL_S,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.store: SessionStore = store if store is not None else _default_store(repo)
        self._llm_call: StructuredCall = llm_call or call_structured
        self._service_getter = service_getter
        self._finance_client = finance_client
        self._justetf_client = justetf_client
        self._case_file_builder = case_file_builder or build_case_file
        self._clock = clock or (lambda: datetime.now(UTC))
        self._session_timeout_s = float(session_timeout_s)
        self._heartbeat_s = float(heartbeat_interval_s)

    # -- dipendenze --------------------------------------------------------

    def _service(self) -> Any:
        if self._service_getter is not None:
            return self._service_getter()
        from ..doctor_policy.service import get_doctor_policy_service

        return get_doctor_policy_service(self.repo)

    def _daily_limit(self) -> int:
        return max(0, int(getattr(self.settings, "doctor_tribunal_daily_limit", DEFAULT_DAILY_LIMIT)))

    def _build_case_file(self, user_id: str, ids: list[int], service: Any) -> dict[str, Any]:
        # Stessa regola delle route X-Ray / Copilot: con l'auto-enrichment spento l'X-Ray legge
        # solo la cache etf_enrichment e non scrive profili justETF.
        auto_enrich = bool(getattr(self.settings, "justetf_xray_auto_enrich_enabled_resolved", False))
        return self._case_file_builder(
            self.repo, user_id, ids, service=service,
            finance_client=self._finance_client,
            justetf_client=self._justetf_client if auto_enrich else None,
        )

    def _limit_info(self, user_id: str, now: datetime) -> dict[str, Any]:
        daily_limit = self._daily_limit()
        used = int(self.store.count_today(user_id, now=now))
        return {
            "daily_limit": daily_limit,
            "used_today": used,
            "remaining": max(0, daily_limit - used),
            "resets_at": _iso_z(next_rome_midnight(now)),
        }

    # -- status / latest ---------------------------------------------------

    def status(self, user_id: str, portfolio_ids: list[Any]) -> dict[str, Any]:
        """TribunalStatus (api-contracts §3.1): non costruisce il fascicolo, non chiama il modello."""
        ids = self._service().resolve_scope(portfolio_ids, user_id)
        scope = build_scope(ids).model_dump()
        tconf = resolve_tribunal_config(self.settings, self.repo, user_id)
        reason: str | None = None
        limit: dict[str, Any] | None = None
        if tconf is None:
            reason = "copilot_not_configured"
        else:
            if tconf.key_source == "server":
                limit = self._limit_info(user_id, self._clock())
            if tconf.config.provider not in STRUCTURED_OUTPUT_PROVIDERS:
                reason = "provider_not_supported"
            elif limit is not None and limit["remaining"] <= 0:
                reason = "daily_limit_reached"
        return {
            "available": reason is None,
            "reason": reason,
            "message": _STATUS_MESSAGES.get(reason) if reason else None,
            "provider": tconf.config.provider if tconf else None,
            "model": tconf.config.model if tconf else None,
            "key_source": tconf.key_source if tconf else None,
            "limit": limit,
            "scope": scope,
        }

    def latest(self, user_id: str, portfolio_ids: list[Any]) -> dict[str, Any]:
        """TribunalLatestResponse (api-contracts §3.3)."""
        service = self._service()
        ids = service.resolve_scope(portfolio_ids, user_id)
        fingerprint = build_scope(ids).fingerprint
        session = self.store.get_latest(user_id, fingerprint)
        if session is None:
            return {"session": None, "current_case_file_hash": None, "data_changed": None}
        current_hash: str | None = None
        case_file = self._build_case_file(user_id, ids, service)
        if case_file.get("status") == "ready":
            current_hash = case_file.get("hash")
        saved_cf = session.get("case_file") or {}
        changed = (
            current_hash is None
            or current_hash != saved_cf.get("hash")
            or session.get("contract_version") != CONTRACT_VERSION
        )
        return {"session": session, "current_case_file_hash": current_hash, "data_changed": changed}

    # -- start -------------------------------------------------------------

    def start(self, user_id: str, portfolio_ids: list[Any], *, force_new: bool = False) -> Iterator[str]:
        """Controlli 2-7 di api-contracts §3.2 subito (AppError prima di restituire), poi lo
        stream SSE (seduta dal vivo o riproduzione). Il flag (1) è delle route."""
        service = self._service()
        ids = service.resolve_scope(portfolio_ids, user_id)          # 2: 400 / 404
        tconf = resolve_tribunal_config(self.settings, self.repo, user_id)
        if tconf is None:                                            # 3
            raise TribunalError("copilot_unavailable", "Copilot non configurato: API key mancante", 503)
        if tconf.config.provider not in STRUCTURED_OUTPUT_PROVIDERS:
            raise TribunalError(
                "provider_not_supported", _STATUS_MESSAGES["provider_not_supported"], 409,
                extra={"provider": tconf.config.provider},
            )
        if not _LOCKS.acquire(user_id):                              # 4
            raise TribunalError(
                "session_in_progress",
                "C'è già una seduta in corso. Attendi che finisca prima di avviarne un'altra.",
                409, retryable=True,
            )
        release = lambda: _LOCKS.release(user_id)  # noqa: E731
        try:
            case_file = self._build_case_file(user_id, ids, service)  # 5
            if case_file.get("status") != "ready":
                raise TribunalError(
                    "empty_portfolio",
                    "Il portafoglio non ha posizioni investite: non c'è ancora nulla da discutere.", 409,
                )
            citable = int((case_file.get("counts") or {}).get("citable", 0))
            if citable < MIN_CITABLE_FACTS:
                raise TribunalError(
                    "insufficient_data",
                    "Il Doctor non ha abbastanza dati affidabili per una seduta. Aggiorna le quotazioni "
                    "o completa i dati degli strumenti e riprova.",
                    409, extra={"citable_facts": citable, "min_citable_facts": MIN_CITABLE_FACTS},
                )
            fingerprint = case_file["scope"]["fingerprint"]
            if not force_new:                                         # 6
                saved = self.store.get_latest(user_id, fingerprint)
                if (
                    saved is not None
                    and saved.get("contract_version") == CONTRACT_VERSION
                    and (saved.get("case_file") or {}).get("hash") == case_file.get("hash")
                ):
                    logger.info(
                        "tribunal.session scope_size=%d reused=%d key_source=%s outcome=%s ms=%d",
                        len(ids), 1, tconf.key_source, "replay", 0,
                    )
                    return _LockedStream(replay_session(saved), release)
            if tconf.key_source == "server":                          # 7
                now = self._clock()
                daily_limit = self._daily_limit()
                used = int(self.store.count_today(user_id, now=now))
                if used >= daily_limit:
                    resets_at = next_rome_midnight(now)
                    retry_after = max(1, int((resets_at - now).total_seconds()))
                    raise TribunalError(
                        "daily_limit_reached",
                        "Hai usato tutte le sedute di oggi disponibili con la chiave del server.",
                        429,
                        extra={"daily_limit": daily_limit, "used_today": used, "resets_at": _iso_z(resets_at)},
                        headers={"Retry-After": str(retry_after)},
                    )
        except BaseException:
            release()
            raise
        return _LockedStream(self._live(user_id, ids, case_file, tconf), release)

    # -- seduta dal vivo ---------------------------------------------------

    def _call_voice(self, phase: str, voice: str | None, config: CopilotConfig,
                    build: Callable[[], Any], verify: Callable[[dict[str, Any]], Any]) -> _VoiceOutcome:
        started = time.monotonic()
        request = build()
        try:
            raw = self._llm_call(
                config, request.system_prompt, request.messages, request.schema,
                schema_name=request.schema_name, timeout_s=CALL_TIMEOUT_S,
            )
        except StructuredOutputError as exc:
            code = exc.code if exc.code in _VOICE_ERROR_CODES else "provider_error"
            logger.warning("tribunal.call phase=%s voice=%s error=%s", phase, voice or "-", type(exc).__name__)
            return _VoiceOutcome(voice, error_code=code, ms=int((time.monotonic() - started) * 1000))
        except Exception as exc:  # noqa: BLE001 - errore imprevisto dell'SDK: come errore del provider
            logger.warning("tribunal.call phase=%s voice=%s error=%s", phase, voice or "-", type(exc).__name__)
            return _VoiceOutcome(voice, error_code="provider_error", ms=int((time.monotonic() - started) * 1000))
        result = verify(raw if isinstance(raw, dict) else {})
        return _VoiceOutcome(voice, result=result, ms=int((time.monotonic() - started) * 1000))

    def _wait_any(self, pending: set[Future], deadline: float) -> Iterator[str]:
        """Attende la prima chiamata conclusa inviando keepalive; ``_SessionTimeout`` alla scadenza."""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _SessionTimeout()
            done, _ = wait(pending, timeout=min(self._heartbeat_s, remaining), return_when=FIRST_COMPLETED)
            if done:
                return done  # type: ignore[return-value]
            if deadline - time.monotonic() <= 0:
                raise _SessionTimeout()
            yield _HEARTBEAT

    @staticmethod
    def _voice_error(phase: str, voice: str, code: str) -> dict[str, Any]:
        return {
            "phase": phase, "voice": voice, "code": code,
            "message": _VOICE_ERROR_MESSAGES[code].format(name=VOICES[voice].name),
            "retryable": code != "unsupported_provider",
        }

    @staticmethod
    def _discard_summary(phase: str, voice: str | None, admitted: int, by_code: dict[str, int]) -> dict[str, Any]:
        return {
            "phase": phase, "voice": voice, "admitted": admitted,
            "discarded": sum(by_code.values()), "by_code": dict(by_code),
        }

    def _log_phase(self, scope_size: int, phase: str, voice: str | None, admitted: int,
                   by_code: dict[str, int], ms: int, error: str | None = None) -> None:
        codes = error and f"error:{error}" or (",".join(f"{c}:{n}" for c, n in by_code.items()) or "-")
        logger.info(
            "tribunal.phase scope_size=%d phase=%s voice=%s admitted=%d discarded=%d codes=%s ms=%d",
            scope_size, phase, voice or "-", admitted, sum(by_code.values()), codes, ms,
        )

    def _run_phase(
        self, phase: str, voices: list[str], submit: Callable[[str], Future], deadline: float,
        scope_size: int, items_event: str, state: dict[str, Any],
    ) -> Iterator[str]:
        """Interroga le voci in parallelo e invia gli elementi di ogni voce appena verificati."""
        futures = {submit(voice): voice for voice in voices}
        pending = set(futures)
        canonical = {v: i for i, v in enumerate(VOICE_IDS)}
        while pending:
            done = yield from self._wait_any(pending, deadline)
            for future in sorted(done, key=lambda f: canonical[futures[f]]):
                pending.discard(future)
                outcome: _VoiceOutcome = future.result()
                voice = futures[future]
                if outcome.error_code is not None:
                    error = self._voice_error(phase, voice, outcome.error_code)
                    state["voice_errors"].append(error)
                    self._log_phase(scope_size, phase, voice, 0, {}, outcome.ms, outcome.error_code)
                    yield sse_event("voice_error", error)
                    continue
                result = outcome.result
                state["admitted"][voice] = list(result.admitted)
                for item in result.admitted:
                    yield sse_event(items_event, item)
                summary = self._discard_summary(phase, voice, len(result.admitted), result.by_code())
                state["discarded"].append(summary)
                self._log_phase(scope_size, phase, voice, len(result.admitted), summary["by_code"], outcome.ms)
                yield sse_event("discarded", summary)

    def _live(self, user_id: str, ids: list[int], case_file: dict[str, Any], tconf: TribunalConfig) -> Iterator[str]:
        started = time.monotonic()
        deadline = started + self._session_timeout_s
        config = tconf.config
        scope_size = len(ids)
        created_at = _iso_z(self._clock())
        session_id = "trb_" + secrets.token_hex(8)
        voices_info = [VOICES[v].info() for v in VOICE_IDS]
        executor = ThreadPoolExecutor(max_workers=len(VOICE_IDS), thread_name_prefix="tribunal")
        phase: str | None = None
        outcome = "error"
        opening: dict[str, Any] = {"admitted": {}, "discarded": [], "voice_errors": []}
        rebuttal: dict[str, Any] = {"admitted": {}, "discarded": [], "voice_errors": []}
        try:
            yield sse_event("session", {
                "session_id": session_id,
                "scope": case_file["scope"],
                "reused": False,
                "created_at": created_at,
                "contract_version": CONTRACT_VERSION,
                "prompt_version": PROMPT_VERSION,
                "provider": config.provider,
                "model": config.model,
                "voices": voices_info,
            })
            yield sse_event("case_file", case_file)

            # -- apertura ---------------------------------------------------
            phase = "apertura"
            yield sse_event("phase", {"phase": phase, "status": "started"})

            def submit_opening(voice: str) -> Future:
                return executor.submit(
                    self._call_voice, "apertura", voice, config,
                    lambda: build_opening_request(voice, case_file),
                    lambda raw: verify_opening(voice, raw, case_file),
                )

            yield from self._run_phase("apertura", list(VOICE_IDS), submit_opening, deadline,
                                       scope_size, "argument", opening)
            yield sse_event("phase", {"phase": phase, "status": "completed"})

            valid = [v for v in VOICE_IDS if opening["admitted"].get(v)]
            arguments = [a for v in VOICE_IDS for a in opening["admitted"].get(v, [])]
            if len(valid) < 2:
                outcome = "too_few_voices"
                yield self._error_event("too_few_voices", phase)
                return

            # -- replica ----------------------------------------------------
            phase = "replica"
            yield sse_event("phase", {"phase": phase, "status": "started"})

            def submit_rebuttal(voice: str) -> Future:
                others = [a for a in arguments if a["voice"] != voice]
                return executor.submit(
                    self._call_voice, "replica", voice, config,
                    lambda: build_rebuttal_request(voice, case_file, others),
                    lambda raw: verify_rebuttals(voice, raw, case_file, arguments),
                )

            yield from self._run_phase("replica", valid, submit_rebuttal, deadline,
                                       scope_size, "rebuttal", rebuttal)
            yield sse_event("phase", {"phase": phase, "status": "completed"})
            rebuttals = [r for v in VOICE_IDS for r in rebuttal["admitted"].get(v, [])]

            # -- sintesi ----------------------------------------------------
            phase = "sintesi"
            yield sse_event("phase", {"phase": phase, "status": "started"})
            future = executor.submit(
                self._call_voice, "sintesi", None, config,
                lambda: build_synthesis_request(case_file, arguments, rebuttals),
                lambda raw: verify_synthesis(raw, case_file, arguments, rebuttals),
            )
            yield from self._wait_any({future}, deadline)
            synth: _VoiceOutcome = future.result()
            if synth.error_code is not None:
                self._log_phase(scope_size, phase, None, 0, {}, synth.ms, synth.error_code)
                outcome = "synthesis_failed"
                yield self._error_event("synthesis_failed", phase)
                return
            verification = synth.result
            synthesis = verification.synthesis
            synth_summary = self._discard_summary(phase, None, verification.admitted_count, verification.by_code())
            self._log_phase(scope_size, phase, None, verification.admitted_count, synth_summary["by_code"], synth.ms)
            yield sse_event("synthesis", synthesis)
            yield sse_event("discarded", synth_summary)
            yield sse_event("phase", {"phase": phase, "status": "completed"})

            # -- salvataggio e fine ----------------------------------------
            discarded = (
                sorted(opening["discarded"], key=lambda d: VOICE_IDS.index(d["voice"]))
                + sorted(rebuttal["discarded"], key=lambda d: VOICE_IDS.index(d["voice"]))
                + [synth_summary]
            )
            voice_errors = [
                {k: e[k] for k in ("phase", "voice", "code", "message")}
                for e in (sorted(opening["voice_errors"], key=lambda e: VOICE_IDS.index(e["voice"]))
                          + sorted(rebuttal["voice_errors"], key=lambda e: VOICE_IDS.index(e["voice"])))
            ]
            totals = {
                "arguments": len(arguments),
                "rebuttals": len(rebuttals),
                "shared_points": len(synthesis.get("shared_points", [])),
                "contested_points": len(synthesis.get("contested_points", [])),
                "open_questions": len(synthesis.get("open_questions", [])),
                "discarded": sum(d["discarded"] for d in discarded),
            }
            session = {
                "session_id": session_id,
                "scope": case_file["scope"],
                "created_at": created_at,
                "completed_at": _iso_z(self._clock()),
                "contract_version": CONTRACT_VERSION,
                "prompt_version": PROMPT_VERSION,
                "provider": config.provider,
                "model": config.model,
                "voices": voices_info,
                "case_file": case_file,
                "arguments": arguments,
                "rebuttals": rebuttals,
                "synthesis": synthesis,
                "discarded": discarded,
                "voice_errors": voice_errors,
                "totals": totals,
            }
            saved = False
            if not isinstance(self.store, NullSessionStore):
                try:
                    self.store.save(user_id, list(ids), session, key_source=tconf.key_source)
                    saved = True
                except Exception as exc:  # noqa: BLE001 - la seduta resta valida per l'utente
                    logger.warning("tribunal.save error=%s", type(exc).__name__)
            outcome = "completed"
            yield sse_event("done", {
                "session_id": session_id,
                "reused": False,
                "saved": saved,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "totals": totals,
            })
        except _SessionTimeout:
            outcome = "timeout"
            yield self._error_event("timeout", phase)
        except GeneratorExit:
            outcome = "disconnected"
            raise
        except Exception as exc:  # noqa: BLE001 - errore imprevisto: evento error, mai il messaggio
            outcome = "internal_error"
            logger.warning("tribunal.session error=%s", type(exc).__name__)
            yield self._error_event("internal_error", phase)
        finally:
            # Chiamate pendenti abbandonate: i loro risultati vengono ignorati.
            executor.shutdown(wait=False, cancel_futures=True)
            logger.info(
                "tribunal.session scope_size=%d reused=%d key_source=%s outcome=%s ms=%d",
                scope_size, 0, tconf.key_source, outcome, int((time.monotonic() - started) * 1000),
            )

    @staticmethod
    def _error_event(code: str, phase: str | None) -> str:
        return sse_event("error", {
            "code": code, "phase": phase, "retryable": _ERROR_RETRYABLE[code], "message": _ERROR_MESSAGES[code],
        })


# ---------------------------------------------------------------------------
# Riproduzione (api-contracts §9.4)
# ---------------------------------------------------------------------------

def replay_session(session: dict[str, Any]) -> Iterator[str]:
    """Eventi di una seduta salvata, in ordine canonico, senza keepalive."""
    yield sse_event("session", {
        "session_id": session["session_id"],
        "scope": session["scope"],
        "reused": True,
        "created_at": session["created_at"],
        "contract_version": session["contract_version"],
        "prompt_version": session["prompt_version"],
        "provider": session["provider"],
        "model": session["model"],
        "voices": session["voices"],
    })
    yield sse_event("case_file", session["case_file"])
    discarded = session.get("discarded") or []
    voice_errors = session.get("voice_errors") or []
    for phase, items_event, items in (
        ("apertura", "argument", session.get("arguments") or []),
        ("replica", "rebuttal", session.get("rebuttals") or []),
    ):
        yield sse_event("phase", {"phase": phase, "status": "started"})
        for voice in VOICE_IDS:
            closing = next((d for d in discarded if d.get("phase") == phase and d.get("voice") == voice), None)
            error = next((e for e in voice_errors if e.get("phase") == phase and e.get("voice") == voice), None)
            if closing is None and error is None:
                continue  # la voce non ha partecipato a questa fase
            for item in items:
                if item.get("voice") == voice:
                    yield sse_event(items_event, item)
            if closing is not None:
                yield sse_event("discarded", closing)
            else:
                code = error.get("code")
                yield sse_event("voice_error", {**error, "retryable": code != "unsupported_provider"})
        yield sse_event("phase", {"phase": phase, "status": "completed"})
    yield sse_event("phase", {"phase": "sintesi", "status": "started"})
    yield sse_event("synthesis", session["synthesis"])
    synth = next((d for d in discarded if d.get("phase") == "sintesi"), None)
    if synth is not None:
        yield sse_event("discarded", synth)
    yield sse_event("phase", {"phase": "sintesi", "status": "completed"})
    yield sse_event("done", {
        "session_id": session["session_id"],
        "reused": True,
        "saved": False,
        "duration_ms": 0,
        "totals": session.get("totals") or {},
    })


__all__ = [
    "CALL_TIMEOUT_S",
    "SESSION_TIMEOUT_S",
    "KeySource",
    "NullSessionStore",
    "SessionStore",
    "TribunalConfig",
    "TribunalError",
    "TribunalOrchestrator",
    "replay_session",
    "resolve_tribunal_config",
    "sse_event",
]
