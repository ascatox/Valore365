"""Orchestratore della seduta del Tribunale (TASK-65, docs/tribunale/api-contracts.md §3, §8, §9).

LLM finto che restituisce le risposte ``raw`` della fixture del contratto, servizio del
Doctor e repository finti; nessuna chiamata di rete. I fake sono riusati da
``test_tribunal_routes.py``.
"""

from __future__ import annotations

import copy
import json
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from app.repository._scope import NOT_FOUND_MESSAGE
from app.services.doctor_policy.errors import InvalidRequest, NotFound
from app.services.doctor_policy.scope import ScopeError, build_scope, normalize_scope_ids

DOCS = Path(__file__).resolve().parents[4] / "docs" / "tribunale"
FIXTURE_JSON = DOCS / "fixtures" / "seduta-esempio.json"
FIXTURE_SSE = DOCS / "fixtures" / "seduta-esempio.sse.txt"
FIXTURE = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
USER = "u1"
OWNED = {19: "EUR", 26: "EUR", 30: "USD"}

_HEADER_RE = re.compile(r"^Tribunale del portafoglio — fase: (apertura|replica|sintesi); voce: (\w+)$")


def make_settings(**overrides: Any) -> SimpleNamespace:
    base = dict(
        copilot_provider="openai", copilot_model="gpt-4o-mini", openai_api_key="sk-server",
        anthropic_api_key="", gemini_api_key="", openrouter_api_key="",
        copilot_local_url="http://localhost:11434/v1", copilot_local_api_key="not-needed",
        copilot_encryption_key="", doctor_tribunal_enabled=True, doctor_tribunal_daily_limit=3,
        doctor_policy_enabled=True, doctor_simulator_enabled=True,
        justetf_xray_auto_enrich_enabled_resolved=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeRepo:
    def __init__(self, provider: str = "", model: str = "", key_enc: str = "") -> None:
        self.provider, self.model, self.key_enc = provider, model, key_enc

    def get_user_settings(self, user_id: str) -> SimpleNamespace:
        return SimpleNamespace(copilot_provider=self.provider, copilot_model=self.model,
                               copilot_api_key_set=bool(self.key_enc))

    def get_user_copilot_api_key_enc(self, user_id: str) -> str:
        return self.key_enc


class FakeService:
    """``resolve_scope`` come il Doctor: 400 per id non validi o valute miste, 404 se non posseduto."""

    def __init__(self, owned: dict[int, str] | None = None) -> None:
        self.owned = dict(OWNED if owned is None else owned)

    def resolve_scope(self, portfolio_ids: Any, user_id: str) -> list[int]:
        try:
            ids = normalize_scope_ids(list(portfolio_ids or []))
        except ScopeError as exc:
            raise InvalidRequest(str(exc)) from exc
        if any(i not in self.owned for i in ids) or user_id != USER:
            raise NotFound(NOT_FOUND_MESSAGE)
        if len({self.owned[i] for i in ids}) > 1:
            raise InvalidRequest("Valute base diverse")
        return ids


class CaseFileBuilder:
    """Fascicolo della fixture con lo scope richiesto; registra gli argomenti ricevuti."""

    def __init__(self, case_file: dict[str, Any] | None = None) -> None:
        self.case_file = copy.deepcopy(case_file or FIXTURE["session"]["case_file"])
        self.calls: list[dict[str, Any]] = []

    def __call__(self, repo: Any, user_id: str, portfolio_ids: Any, **kwargs: Any) -> dict[str, Any]:
        ids = kwargs["service"].resolve_scope(portfolio_ids, user_id)
        self.calls.append({"user_id": user_id, "ids": ids, **kwargs})
        cf = copy.deepcopy(self.case_file)
        cf["scope"] = build_scope(ids).model_dump()
        if len(ids) > 1:
            cf["notes"] = [f"Vista aggregata di {len(ids)} portafogli."] + list(cf.get("notes") or [])
        return cf


class RecordingStore:
    def __init__(self, latest: dict[str, Any] | None = None, used_today: int = 0) -> None:
        self.latest = latest
        self.used_today = used_today
        self.saved: list[tuple[str, list[int], dict[str, Any], str]] = []

    def get_latest(self, user_id: str, scope_fingerprint: str) -> dict[str, Any] | None:
        if self.latest and self.latest["scope"]["fingerprint"] == scope_fingerprint:
            return copy.deepcopy(self.latest)
        return None

    def save(self, user_id: str, portfolio_ids: list[int], session: dict[str, Any], *, key_source: str) -> None:
        self.saved.append((user_id, list(portfolio_ids), copy.deepcopy(session), key_source))

    def count_today(self, user_id: str, *, now: Any = None) -> int:
        return self.used_today


class FakeLLM:
    """Stessa firma di ``call_structured``; riconosce fase e voce dalla prima riga del prompt.

    ``behaviour[(phase, voice)]`` può essere un'eccezione da sollevare, un dict da restituire
    o una funzione chiamata prima di restituire la risposta ``raw`` della fixture.
    """

    def __init__(self, raw: dict[str, Any] | None = None,
                 behaviour: dict[tuple[str, str], Any] | None = None) -> None:
        self.raw = copy.deepcopy(raw or FIXTURE["raw"])
        self.behaviour = dict(behaviour or {})
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def __call__(self, config: Any, system_prompt: str, messages: list[dict[str, str]],
                 schema: dict[str, Any], *, schema_name: str, timeout_s: float = 45.0,
                 max_tokens: int = 2048) -> dict[str, Any]:
        match = _HEADER_RE.match(system_prompt.splitlines()[0])
        assert match, "prima riga del prompt di sistema non conforme a §8.3"
        phase, voice = match.group(1), match.group(2)
        with self._lock:
            self.calls.append({"phase": phase, "voice": voice, "schema_name": schema_name,
                               "timeout_s": timeout_s, "messages": messages, "provider": config.provider})
        action = self.behaviour.get((phase, voice))
        if isinstance(action, BaseException):
            raise action
        if isinstance(action, dict):
            return copy.deepcopy(action)
        if callable(action):
            action()
        if phase == "sintesi":
            return copy.deepcopy(self.raw["sintesi"])
        return copy.deepcopy(self.raw[phase][voice])


def gate(order: list[str], phase: str, current: str, events: dict[str, threading.Event],
         timeout: float = 5.0) -> Callable[[], None]:
    """Fa completare le voci di una fase nell'ordine ``order``."""

    def wait_turn() -> None:
        index = order.index(current)
        if index > 0:
            assert events[order[index - 1]].wait(timeout), f"{phase}: {current} in attesa"
            time.sleep(0.02)
        events[current].set()

    return wait_turn


def parse_sse(chunks: Any) -> tuple[list[dict[str, Any]], int]:
    """(eventi, numero di keepalive) di uno stream SSE."""
    text = "".join(chunks)
    events: list[dict[str, Any]] = []
    keepalives = 0
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        assert "\n" not in block, f"evento su più righe: {block[:80]!r}"
        if block == ": keepalive":
            keepalives += 1
            continue
        assert block.startswith("data: "), block[:80]
        events.append(json.loads(block[len("data: "):]))
    return events, keepalives


def fixture_events() -> list[dict[str, Any]]:
    events, _ = parse_sse([FIXTURE_SSE.read_text(encoding="utf-8")])
    return events


# ---------------------------------------------------------------------------
# Helpers dei test
# ---------------------------------------------------------------------------

import logging  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402

from app.copilot.structured import (  # noqa: E402
    StructuredOutputProviderError,
    StructuredOutputSchemaError,
    StructuredOutputTimeout,
)
from app.errors import AppError  # noqa: E402
from app.services.tribunal import orchestrator as orch_module  # noqa: E402
from app.services.tribunal.orchestrator import (  # noqa: E402
    CALL_TIMEOUT_S,
    SESSION_TIMEOUT_S,
    NullSessionStore,
    TribunalOrchestrator,
    next_rome_midnight,
    replay_session,
    resolve_tribunal_config,
    sse_event,
)

APERTURA_ORDER = ["prudente", "indicizzatore", "fattoriale"]   # ordine di completamento della fixture
REPLICA_ORDER = ["fattoriale", "indicizzatore", "prudente"]
CANONICAL = ["indicizzatore", "fattoriale", "prudente"]


def ordered_llm(**kwargs: Any) -> FakeLLM:
    """LLM finto che completa le voci nell'ordine dello stream della fixture."""
    ev_a = {v: threading.Event() for v in APERTURA_ORDER}
    ev_r = {v: threading.Event() for v in REPLICA_ORDER}
    behaviour = {("apertura", v): gate(APERTURA_ORDER, "apertura", v, ev_a) for v in APERTURA_ORDER}
    behaviour.update({("replica", v): gate(REPLICA_ORDER, "replica", v, ev_r) for v in REPLICA_ORDER})
    behaviour.update(kwargs.pop("behaviour", {}))
    return FakeLLM(behaviour=behaviour, **kwargs)


def make_orchestrator(llm: Any = None, *, store: Any = None, repo: Any = None, settings: Any = None,
                      builder: Any = None, **kwargs: Any) -> TribunalOrchestrator:
    service = FakeService()
    return TribunalOrchestrator(
        repo or FakeRepo(), settings or make_settings(),
        store=store if store is not None else RecordingStore(),
        llm_call=llm or FakeLLM(),
        service_getter=lambda: service,
        case_file_builder=builder or CaseFileBuilder(),
        **kwargs,
    )


def normalize(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = copy.deepcopy(events)
    for ev in out:
        if ev["type"] == "session":
            ev["content"]["session_id"] = ev["content"]["created_at"] = None
        if ev["type"] == "done":
            ev["content"]["session_id"] = ev["content"]["duration_ms"] = None
    return out


def canonical_order(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Riordina le voci di apertura e replica in ordine canonico (l'ordine tra voci della
    stessa fase è quello di completamento e può variare, api-contracts §8.1)."""
    out: list[dict[str, Any]] = []
    chunk: list[dict[str, Any]] = []
    chunks: list[list[dict[str, Any]]] | None = None
    for ev in events:
        c = ev["content"]
        if ev["type"] == "phase" and c["phase"] in ("apertura", "replica"):
            if c["status"] == "started":
                out.append(ev)
                chunks = []
                continue
            assert chunks is not None and not chunk
            chunks.sort(key=lambda ch: CANONICAL.index(ch[-1]["content"]["voice"]))
            out.extend(e for ch in chunks for e in ch)
            chunks = None
            out.append(ev)
            continue
        if chunks is not None:
            chunk.append(ev)
            if ev["type"] in ("discarded", "voice_error"):
                chunks.append(chunk)
                chunk = []
            continue
        out.append(ev)
    return out


def run_stream(orch: TribunalOrchestrator, ids: list[int] | None = None, **kwargs: Any):
    return parse_sse(orch.start(USER, ids or [19], **kwargs))


def types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


def check_grammar(events: list[dict[str, Any]]) -> None:
    """Garanzie di api-contracts §9.2."""
    assert events[0]["type"] == "session" and events[1]["type"] == "case_file"
    assert [e["type"] for e in events].count("done") + [e["type"] for e in events].count("error") == 1
    assert events[-1]["type"] in ("done", "error")
    phase = None
    closed: dict[tuple[str, str], int] = {}
    for ev in events[2:]:
        c = ev["content"]
        assert isinstance(c, dict)
        if ev["type"] == "phase":
            phase = c["phase"] if c["status"] == "started" else None
        elif ev["type"] in ("argument", "rebuttal"):
            assert phase == c["phase"] and (phase, c["voice"]) not in closed
        elif ev["type"] in ("discarded", "voice_error") and c["voice"] is not None:
            assert phase == c["phase"]
            key = (c["phase"], c["voice"])
            assert key not in closed, "una sola chiusura per voce e fase"
            closed[key] = 1


@pytest.fixture(autouse=True)
def _release_locks():
    yield
    orch_module._LOCKS._active.clear()


# ---------------------------------------------------------------------------
# Seduta completa contro la fixture
# ---------------------------------------------------------------------------

def test_sse_event_format():
    line = sse_event("phase", {"phase": "apertura", "status": "started"})
    assert line == 'data: {"type": "phase", "content": {"phase": "apertura", "status": "started"}}\n\n'
    assert sse_event("x", {"t": "è"}).count("\n") == 2 and "è" in sse_event("x", {"t": "è"})


def test_full_session_matches_fixture_stream_exactly():
    store = RecordingStore()
    llm = ordered_llm()
    events, _ = run_stream(make_orchestrator(llm, store=store))
    expected = fixture_events()
    assert len(events) == 30
    assert normalize(events) == normalize(expected)
    check_grammar(events)
    session = events[0]["content"]
    assert re.fullmatch(r"trb_[0-9a-f]{16}", session["session_id"])
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", session["created_at"])
    assert events[-1]["content"]["session_id"] == session["session_id"]
    assert events[-1]["content"]["saved"] is True
    # 7 chiamate: 3 aperture + 3 repliche + 1 sintesi, ognuna con CALL_TIMEOUT_S.
    assert len(llm.calls) == 7 and {c["timeout_s"] for c in llm.calls} == {CALL_TIMEOUT_S}
    assert [c["schema_name"] for c in llm.calls].count("tribunal_opening") == 3
    assert [c["schema_name"] for c in llm.calls][-1] == "tribunal_synthesis"


def test_full_session_any_completion_order_matches_fixture():
    events, _ = run_stream(make_orchestrator(FakeLLM()))
    assert normalize(canonical_order(events)) == normalize(canonical_order(fixture_events()))
    check_grammar(events)


def test_saved_session_matches_fixture_session():
    store = RecordingStore()
    events, _ = run_stream(make_orchestrator(FakeLLM(), store=store))
    assert len(store.saved) == 1
    user_id, ids, session, key_source = store.saved[0]
    assert (user_id, ids, key_source) == (USER, [19], "server")
    expected = copy.deepcopy(FIXTURE["session"])
    for key in ("session_id", "created_at", "completed_at"):
        assert session.pop(key) and expected.pop(key)
    assert session == expected
    assert events[-1]["content"]["totals"] == expected["totals"]


def test_aggregate_scope_session():
    builder = CaseFileBuilder()
    events, _ = run_stream(make_orchestrator(FakeLLM(), builder=builder), ids=[26, 19, 26])
    scope = {"portfolio_ids": [19, 26], "scope_type": "aggregate", "fingerprint": "p:19,26"}
    assert events[0]["content"]["scope"] == scope
    assert events[1]["content"]["scope"] == scope
    assert events[-1]["type"] == "done"
    assert builder.calls[0]["ids"] == [19, 26]


def test_null_store_done_not_saved():
    events, _ = run_stream(make_orchestrator(FakeLLM(), store=NullSessionStore()))
    assert events[-1]["type"] == "done" and events[-1]["content"]["saved"] is False


def test_rebuttal_and_synthesis_receive_only_admitted_items():
    llm = FakeLLM()
    run_stream(make_orchestrator(llm))
    replica = [c for c in llm.calls if c["phase"] == "replica"]
    for call in replica:
        content = call["messages"][0]["content"]
        own_code = {"indicizzatore": "IND", "fattoriale": "FAT", "prudente": "PRU"}[call["voice"]]
        assert f'"A-{own_code}-1"' not in content
        assert "A-" in content
    synthesis = [c for c in llm.calls if c["phase"] == "sintesi"][0]["messages"][0]["content"]
    assert '"R-IND-2"' in synthesis and '"text":' not in synthesis


# ---------------------------------------------------------------------------
# Parallelismo e invio immediato (AC #2)
# ---------------------------------------------------------------------------

def test_voices_run_in_parallel_and_items_are_sent_as_soon_as_verified():
    barrier = threading.Barrier(3, timeout=5)
    sent = threading.Event()

    def ind() -> None:
        barrier.wait()

    def slow() -> None:
        barrier.wait()
        # Il fattoriale e il prudente finiscono solo dopo che il client ha ricevuto gli
        # argomenti dell'indicizzatore: se l'orchestratore aspettasse tutte le voci, il
        # test andrebbe in timeout.
        assert sent.wait(5), "argomenti dell'indicizzatore non inviati prima delle altre voci"

    llm = FakeLLM(behaviour={("apertura", "indicizzatore"): ind, ("apertura", "fattoriale"): slow,
                             ("apertura", "prudente"): slow})
    stream = make_orchestrator(llm).start(USER, [19])
    events: list[dict[str, Any]] = []
    for chunk in stream:
        if chunk.startswith("data: "):
            ev = json.loads(chunk[6:])
            events.append(ev)
            if ev["type"] == "discarded" and ev["content"]["voice"] == "indicizzatore":
                sent.set()
    seq = [(e["type"], e["content"].get("voice")) for e in events]
    first_other = min(seq.index(("argument", "fattoriale")), seq.index(("argument", "prudente")))
    assert seq.index(("discarded", "indicizzatore")) < first_other
    assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# Fallimenti (AC #3)
# ---------------------------------------------------------------------------

def test_voice_failure_continues_with_other_voices():
    store = RecordingStore()
    llm = FakeLLM(behaviour={("apertura", "fattoriale"): StructuredOutputTimeout("x", provider="openai")})
    events, _ = run_stream(make_orchestrator(llm, store=store))
    check_grammar(events)
    errors = [e["content"] for e in events if e["type"] == "voice_error"]
    assert errors == [{
        "phase": "apertura", "voice": "fattoriale", "code": "timeout",
        "message": "Il fattoriale non ha risposto in tempo: la seduta prosegue con le altre voci.",
        "retryable": True,
    }]
    # In replica partecipano solo le voci valide.
    assert sorted(c["voice"] for c in llm.calls if c["phase"] == "replica") == ["indicizzatore", "prudente"]
    assert not any(e["type"] == "discarded" and e["content"]["voice"] == "fattoriale" for e in events)
    assert events[-1]["type"] == "done"
    session = store.saved[0][2]
    assert session["voice_errors"] == [{k: errors[0][k] for k in ("phase", "voice", "code", "message")}]
    assert [d["voice"] for d in session["discarded"] if d["phase"] == "apertura"] == ["indicizzatore", "prudente"]
    assert not any(a["voice"] == "fattoriale" for a in session["arguments"])


@pytest.mark.parametrize(("exc", "code", "fragment"), [
    (StructuredOutputSchemaError("x", provider="openai"), "schema_mismatch", "in un formato non valido"),
    (StructuredOutputProviderError("boom secret", provider="openai"), "provider_error", "errore del servizio AI"),
    (RuntimeError("sdk crash"), "provider_error", "errore del servizio AI"),
])
def test_voice_error_codes(exc, code, fragment):
    llm = FakeLLM(behaviour={("replica", "prudente"): exc})
    events, _ = run_stream(make_orchestrator(llm))
    err = [e["content"] for e in events if e["type"] == "voice_error"][0]
    assert (err["phase"], err["voice"], err["code"]) == ("replica", "prudente", code)
    assert fragment in err["message"] and "secret" not in err["message"]
    assert events[-1]["type"] == "done"   # la replica è opzionale


def test_all_arguments_discarded_continues():
    bad = {"arguments": [{"theme": "costi", "stance": "neutro", "text": "Il TER vale 0,19% ed è basso, davvero.",
                          "fact_ids": ["F9"]}]}
    llm = FakeLLM(behaviour={("apertura", "prudente"): bad})
    events, _ = run_stream(make_orchestrator(llm))
    disc = [e["content"] for e in events if e["type"] == "discarded" and e["content"]["voice"] == "prudente"
            and e["content"]["phase"] == "apertura"]
    assert disc == [{"phase": "apertura", "voice": "prudente", "admitted": 0, "discarded": 1,
                     "by_code": {"cifra_libera": 1}}]
    assert "prudente" not in {c["voice"] for c in llm.calls if c["phase"] == "replica"}
    assert events[-1]["type"] == "done"


def test_too_few_voices_ends_session():
    store = RecordingStore()
    bad = {"arguments": [{"theme": "costi", "stance": "neutro", "text": "Testo senza fatti validi qui.",
                          "fact_ids": []}]}
    llm = FakeLLM(behaviour={
        ("apertura", "prudente"): bad,
        ("apertura", "fattoriale"): StructuredOutputProviderError("x", provider="openai"),
    })
    events, _ = run_stream(make_orchestrator(llm, store=store))
    check_grammar(events)
    assert types(events)[-2:] == ["phase", "error"]
    assert events[-2]["content"] == {"phase": "apertura", "status": "completed"}
    assert events[-1]["content"] == {
        "code": "too_few_voices", "phase": "apertura", "retryable": True,
        "message": "Meno di due voci hanno prodotto argomenti verificabili: la seduta è stata interrotta. "
                   "Riprova tra poco.",
    }
    assert not [c for c in llm.calls if c["phase"] != "apertura"]
    assert store.saved == []


def test_synthesis_failure():
    store = RecordingStore()
    llm = FakeLLM(behaviour={("sintesi", "sintesi"): StructuredOutputTimeout("x", provider="openai")})
    events, _ = run_stream(make_orchestrator(llm, store=store))
    check_grammar(events)
    assert types(events)[-2:] == ["phase", "error"]
    assert events[-2]["content"] == {"phase": "sintesi", "status": "started"}
    assert events[-1]["content"]["code"] == "synthesis_failed"
    assert events[-1]["content"]["phase"] == "sintesi" and events[-1]["content"]["retryable"] is True
    assert store.saved == []


def test_synthesis_all_discarded_is_still_a_valid_synthesis():
    store = RecordingStore()
    empty = {"shared_points": [], "contested_points": [], "open_questions": [{"text": "Compra subito VWCE?"}]}
    llm = FakeLLM(behaviour={("sintesi", "sintesi"): empty})
    events, _ = run_stream(make_orchestrator(llm, store=store))
    synth = [e["content"] for e in events if e["type"] == "synthesis"][0]
    assert synth == {"shared_points": [], "contested_points": [], "open_questions": []}
    disc = [e["content"] for e in events if e["type"] == "discarded" and e["content"]["phase"] == "sintesi"][0]
    assert disc["voice"] is None and disc["admitted"] == 0 and disc["discarded"] == 1
    assert events[-1]["type"] == "done" and len(store.saved) == 1


def test_unexpected_exception_is_internal_error(monkeypatch):
    def boom(*_a, **_k):
        raise KeyError("text of the case file")

    monkeypatch.setattr(orch_module, "verify_opening", boom)
    events, _ = run_stream(make_orchestrator(FakeLLM()))
    assert events[-1] == {"type": "error", "content": {
        "code": "internal_error", "phase": "apertura", "retryable": False,
        "message": "Errore imprevisto durante la seduta."}}


# ---------------------------------------------------------------------------
# Timeout e keepalive (AC #4)
# ---------------------------------------------------------------------------

def test_constants():
    assert (CALL_TIMEOUT_S, SESSION_TIMEOUT_S) == (45, 180)
    assert orch_module.HEARTBEAT_INTERVAL_S == 10


def test_session_timeout_emits_error_and_keepalives():
    store = RecordingStore()
    release = threading.Event()
    llm = FakeLLM(behaviour={("apertura", "prudente"): lambda: release.wait(5)})
    orch = make_orchestrator(llm, store=store, session_timeout_s=0.4, heartbeat_interval_s=0.05)
    started = time.monotonic()
    events, keepalives = run_stream(orch)
    release.set()
    assert time.monotonic() - started < 3
    check_grammar(events)
    assert keepalives >= 2
    assert events[-1]["content"]["code"] == "timeout" and events[-1]["content"]["phase"] == "apertura"
    assert events[-1]["content"]["retryable"] is True
    # Le voci già concluse restano valide e inviate.
    assert any(e["type"] == "argument" and e["content"]["voice"] == "indicizzatore" for e in events)
    assert store.saved == []


def test_keepalive_during_waits():
    llm = FakeLLM(behaviour={("sintesi", "sintesi"): lambda: time.sleep(0.3)})
    text = "".join(make_orchestrator(llm, heartbeat_interval_s=0.05).start(USER, [19]))
    assert text.count(": keepalive\n\n") >= 3
    events, _ = parse_sse([text])
    assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# Controlli prima dello stream (api-contracts §3.2)
# ---------------------------------------------------------------------------

def _app_error(fn) -> AppError:
    with pytest.raises(AppError) as info:
        fn()
    return info.value


def test_scope_of_another_user_is_not_found_before_anything():
    llm = FakeLLM()
    builder = CaseFileBuilder()
    orch = make_orchestrator(llm, builder=builder)
    for call in (lambda: orch.start(USER, [99]), lambda: orch.status(USER, [99]),
                 lambda: orch.latest(USER, [19, 99]), lambda: orch.start("other-user", [19])):
        err = _app_error(call)
        assert (err.status_code, err.code) == (404, "not_found")
    assert llm.calls == [] and builder.calls == []


def test_invalid_scope_and_mixed_currencies():
    orch = make_orchestrator()
    for ids in ([0], ["abc"], [], [19, 30]):
        err = _app_error(lambda: orch.start(USER, ids))
        assert (err.status_code, err.code) == (400, "invalid_request")


def test_copilot_not_configured_and_provider_not_supported():
    err = _app_error(lambda: make_orchestrator(settings=make_settings(copilot_provider="")).start(USER, [19]))
    assert (err.status_code, err.code) == (503, "copilot_unavailable")
    err = _app_error(lambda: make_orchestrator(settings=make_settings(copilot_provider="local")).start(USER, [19]))
    assert (err.status_code, err.code) == (409, "provider_not_supported")
    assert err.details["provider"] == "local" and err.details["retryable"] is False


def test_session_in_progress_and_lock_release():
    orch = make_orchestrator(FakeLLM())
    stream = orch.start(USER, [19])
    err = _app_error(lambda: orch.start(USER, [26]))
    assert (err.status_code, err.code) == (409, "session_in_progress")
    assert err.details["retryable"] is True
    list(stream)                                   # fine dello stream → lock libero
    list(orch.start(USER, [19]))
    # Chiusura anticipata (disconnessione del client).
    stream = orch.start(USER, [19])
    next(stream)
    stream.close()
    list(orch.start(USER, [19]))
    # Stream mai letto e abbandonato.
    stream = orch.start(USER, [19])
    del stream
    list(orch.start(USER, [19]))
    # Un errore prima dello stream libera il lock.
    empty = CaseFileBuilder({**FIXTURE["session"]["case_file"], "status": "empty_portfolio", "facts": []})
    orch2 = make_orchestrator(builder=empty)
    _app_error(lambda: orch2.start(USER, [19]))
    assert not orch_module._LOCKS.active(USER)


def test_disconnect_abandons_calls_and_saves_nothing():
    store = RecordingStore()
    orch = make_orchestrator(FakeLLM(), store=store)
    stream = orch.start(USER, [19])
    for chunk in stream:
        if '"type": "argument"' in chunk:
            break
    stream.close()
    assert store.saved == [] and not orch_module._LOCKS.active(USER)


def test_empty_portfolio_and_insufficient_data():
    cf = FIXTURE["session"]["case_file"]
    empty = CaseFileBuilder({**cf, "status": "empty_portfolio", "facts": [], "counts": {"total": 0, "citable": 0}})
    err = _app_error(lambda: make_orchestrator(builder=empty).start(USER, [19]))
    assert (err.status_code, err.code) == (409, "empty_portfolio")
    few = CaseFileBuilder({**cf, "counts": {"total": 37, "citable": 5}})
    err = _app_error(lambda: make_orchestrator(builder=few).start(USER, [19]))
    assert (err.status_code, err.code) == (409, "insufficient_data")
    assert err.details["citable_facts"] == 5 and err.details["min_citable_facts"] == 6


def test_daily_limit_reached_with_server_key():
    now = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)
    llm = FakeLLM()
    orch = make_orchestrator(llm, store=RecordingStore(used_today=3), clock=lambda: now)
    err = _app_error(lambda: orch.start(USER, [19]))
    assert (err.status_code, err.code) == (429, "daily_limit_reached")
    assert err.details["daily_limit"] == 3 and err.details["used_today"] == 3
    assert err.details["resets_at"] == "2026-11-10T23:00:00Z"
    assert err.headers["Retry-After"] == str(9 * 3600)
    assert llm.calls == [] and not orch_module._LOCKS.active(USER)
    # Limite 0 = niente sedute con la chiave del server.
    orch = make_orchestrator(settings=make_settings(doctor_tribunal_daily_limit=0))
    assert _app_error(lambda: orch.start(USER, [19])).code == "daily_limit_reached"


def test_user_key_has_no_daily_limit():
    key = Fernet.generate_key().decode()
    settings = make_settings(copilot_encryption_key=key)
    enc = Fernet(key.encode()).encrypt(b"sk-user").decode()
    repo = FakeRepo(provider="anthropic", model="claude-x", key_enc=enc)
    store = RecordingStore(used_today=99)
    llm = FakeLLM()
    events, _ = run_stream(make_orchestrator(llm, store=store, repo=repo, settings=settings))
    assert events[0]["content"]["provider"] == "anthropic" and events[0]["content"]["model"] == "claude-x"
    assert events[-1]["type"] == "done" and store.saved[0][3] == "user"
    assert {c["provider"] for c in llm.calls} == {"anthropic"}


def test_reuse_replays_saved_session_without_calling_the_model():
    saved = copy.deepcopy(FIXTURE["session"])
    llm = FakeLLM()
    store = RecordingStore(latest=saved, used_today=3)       # anche a limite esaurito
    events, keepalives = run_stream(make_orchestrator(llm, store=store))
    assert llm.calls == [] and store.saved == [] and keepalives == 0
    check_grammar(events)
    assert events[0]["content"]["reused"] is True
    assert events[0]["content"]["session_id"] == saved["session_id"]
    assert events[-1]["content"] == {"session_id": saved["session_id"], "reused": True, "saved": False,
                                     "duration_ms": 0, "totals": saved["totals"]}
    # Riproduzione = stessa grammatica in ordine canonico, contenuti identici.
    expected = canonical_order(fixture_events())
    expected[0]["content"]["reused"] = True
    expected[-1]["content"].update(reused=True, saved=False, duration_ms=0)
    assert events == expected
    # force_new ignora la seduta salvata (e qui il limite è esaurito).
    err = _app_error(lambda: make_orchestrator(llm, store=store).start(USER, [19], force_new=True))
    assert err.code == "daily_limit_reached"


def test_reuse_requires_same_hash_and_contract_version():
    for change in ({"contract_version": "tribunale-0.9"},
                   {"case_file": {**FIXTURE["session"]["case_file"], "hash": "0" * 64}}):
        saved = {**copy.deepcopy(FIXTURE["session"]), **change}
        llm = FakeLLM()
        events, _ = run_stream(make_orchestrator(llm, store=RecordingStore(latest=saved)))
        assert events[0]["content"]["reused"] is False and len(llm.calls) == 7


def test_replay_with_voice_error():
    saved = copy.deepcopy(FIXTURE["session"])
    saved["arguments"] = [a for a in saved["arguments"] if a["voice"] != "fattoriale"]
    saved["discarded"] = [d for d in saved["discarded"] if not (d["phase"] == "apertura" and d["voice"] == "fattoriale")]
    saved["voice_errors"] = [{"phase": "apertura", "voice": "fattoriale", "code": "timeout", "message": "m"}]
    events, _ = parse_sse(replay_session(saved))
    check_grammar(events)
    ve = [e["content"] for e in events if e["type"] == "voice_error"]
    assert ve == [{"phase": "apertura", "voice": "fattoriale", "code": "timeout", "message": "m", "retryable": True}]


# ---------------------------------------------------------------------------
# status / latest / configurazione
# ---------------------------------------------------------------------------

def test_status_server_key_with_limit():
    now = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)
    orch = make_orchestrator(store=RecordingStore(used_today=1), clock=lambda: now)
    assert orch.status(USER, ["19"]) == {
        "available": True, "reason": None, "message": None, "provider": "openai", "model": "gpt-4o-mini",
        "key_source": "server",
        "limit": {"daily_limit": 3, "used_today": 1, "remaining": 2, "resets_at": "2026-11-10T23:00:00Z"},
        "scope": {"portfolio_ids": [19], "scope_type": "single", "fingerprint": "p:19"},
    }


def test_status_reasons():
    st = make_orchestrator(settings=make_settings(copilot_provider="")).status(USER, [19])
    assert (st["available"], st["reason"], st["provider"], st["key_source"], st["limit"]) == \
        (False, "copilot_not_configured", None, None, None)
    assert "Impostazioni → Copilot" in st["message"]
    st = make_orchestrator(settings=make_settings(copilot_provider="local")).status(USER, [19])
    assert (st["available"], st["reason"], st["provider"]) == (False, "provider_not_supported", "local")
    st = make_orchestrator(store=RecordingStore(used_today=3)).status(USER, [19, 26])
    assert (st["available"], st["reason"], st["limit"]["remaining"]) == (False, "daily_limit_reached", 0)
    assert st["scope"]["scope_type"] == "aggregate"
    key = Fernet.generate_key().decode()
    enc = Fernet(key.encode()).encrypt(b"sk-user").decode()
    st = make_orchestrator(repo=FakeRepo("gemini", "", enc), settings=make_settings(copilot_encryption_key=key),
                           store=RecordingStore(used_today=3)).status(USER, [19])
    assert (st["available"], st["key_source"], st["limit"], st["provider"]) == (True, "user", None, "gemini")


def test_resolve_tribunal_config_key_source():
    key = Fernet.generate_key().decode()
    settings = make_settings(copilot_encryption_key=key)
    enc = Fernet(key.encode()).encrypt(b"sk-user").decode()
    assert resolve_tribunal_config(settings, FakeRepo("openai", "", enc), USER).key_source == "user"
    # Chiave che non si decifra → ramo del server.
    tc = resolve_tribunal_config(settings, FakeRepo("openai", "", "garbage"), USER)
    assert tc.key_source == "server" and tc.config.api_key == "sk-server"
    assert resolve_tribunal_config(make_settings(copilot_provider=""), FakeRepo(), USER) is None


def test_next_rome_midnight_handles_dst():
    assert next_rome_midnight(datetime(2026, 7, 1, 21, 59, tzinfo=timezone.utc)) == \
        datetime(2026, 7, 1, 22, 0, tzinfo=timezone.utc)
    assert next_rome_midnight(datetime(2026, 11, 10, 23, 30, tzinfo=timezone.utc)) == \
        datetime(2026, 11, 11, 23, 0, tzinfo=timezone.utc)


def test_latest_with_null_store_and_with_saved_session():
    orch = make_orchestrator(store=NullSessionStore())
    assert orch.latest(USER, [19]) == {"session": None, "current_case_file_hash": None, "data_changed": None}
    saved = copy.deepcopy(FIXTURE["session"])
    out = make_orchestrator(store=RecordingStore(latest=saved)).latest(USER, [19])
    assert out["current_case_file_hash"] == saved["case_file"]["hash"] and out["data_changed"] is False
    changed = CaseFileBuilder({**saved["case_file"], "hash": "1" * 64})
    out = make_orchestrator(store=RecordingStore(latest=saved), builder=changed).latest(USER, [19])
    assert out["data_changed"] is True and out["current_case_file_hash"] == "1" * 64
    empty = CaseFileBuilder({**saved["case_file"], "status": "empty_portfolio", "facts": []})
    out = make_orchestrator(store=RecordingStore(latest=saved), builder=empty).latest(USER, [19])
    assert out["current_case_file_hash"] is None and out["data_changed"] is True


def test_default_case_file_builder_gets_clients_with_justetf_rule(monkeypatch):
    calls: list[dict[str, Any]] = []
    cf = FIXTURE["session"]["case_file"]

    def fake_build(repo, user_id, ids, **kwargs):
        calls.append(kwargs)
        return copy.deepcopy(cf)

    monkeypatch.setattr(orch_module, "build_case_file", fake_build)
    service = FakeService()
    fin, jet = object(), object()
    for auto, expected in ((False, None), (True, jet)):
        orch = TribunalOrchestrator(
            FakeRepo(), make_settings(justetf_xray_auto_enrich_enabled_resolved=auto),
            store=RecordingStore(latest=copy.deepcopy(FIXTURE["session"])),
            llm_call=FakeLLM(), service_getter=lambda: service, finance_client=fin, justetf_client=jet,
        )
        list(orch.start(USER, [19]))
        assert calls[-1]["finance_client"] is fin and calls[-1]["justetf_client"] is expected
        assert calls[-1]["service"] is service


# ---------------------------------------------------------------------------
# Log (AC #7)
# ---------------------------------------------------------------------------

def test_logs_contain_only_counts_durations_and_codes(caplog):
    caplog.set_level(logging.DEBUG)
    llm = FakeLLM(behaviour={("replica", "prudente"): StructuredOutputProviderError("payload VWCE.DE", provider="openai")})
    run_stream(make_orchestrator(llm))
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "tribunal.phase" in logs and "tribunal.session" in logs
    assert "codes=cifra_libera:1" in logs and "outcome=completed" in logs
    forbidden = ["VWCE", "IE00", "TER medio", "Quota azionaria", "payload", "{F"]
    forbidden += [a["text"][:30] for a in FIXTURE["session"]["arguments"]]
    forbidden += [f["label"] for f in FIXTURE["session"]["case_file"]["facts"]]
    for needle in forbidden:
        assert needle not in logs, needle
