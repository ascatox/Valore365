#!/usr/bin/env python3
"""Valutazione del Tribunale contro un provider (TASK-71, opzionale).

Esegue una o più sedute complete e riporta, per voce, fase e codice di scarto, quanti
argomenti/repliche/punti il verificatore ha ammesso e quanti ha scartato, più gli errori delle
voci e la durata. Serve a confrontare modifiche ai prompt (``PROMPT_VERSION``) o al modello:
a parità di fascicoli, meno scarti = prompt più aderente alle regole.

Due sorgenti, stessa analisi degli eventi SSE:

- **in processo** (default): orchestratore reale (``TribunalOrchestrator`` → ``call_structured``
  → verificatore) sui fascicoli di esempio, senza database. Fascicoli: la seduta d'esempio
  ``docs/tribunale/fixtures/seduta-esempio.json`` più ogni ``--case-file`` (JSON di un
  ``CaseFile``, es. salvato da ``GET /api/doctor/tribunal/sessions/latest`` → ``session.case_file``).
  Provider e modello da ``--provider``/``--model``; la chiave da ``--api-key-env`` (default la
  variabile del provider: ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, ``GEMINI_API_KEY``,
  ``OPENROUTER_API_KEY``); ``--base-url`` imposta ``OPENAI_BASE_URL`` (finto LLM o gateway).
- **backend** (``--api http://127.0.0.1:8000/api --scope 1 --scope 1,2``): ``POST
  /doctor/tribunal/sessions`` con ``force_new`` su un backend già avviato, con il provider
  configurato lì (consuma le sedute del limite giornaliero se la chiave è del server).

``--dry-run`` non chiama nessun modello: costruisce i prompt di ogni voce e fase sui fascicoli e
stampa il piano (chiamate, dimensione dei prompt, schemi). ATTENZIONE: senza ``--dry-run`` e senza
``--base-url`` verso un finto LLM, ogni seduta fa 7 chiamate a pagamento al provider.

Esempi:
    # a secco (nessuna chiamata)
    python scripts/e2e/tribunal_eval.py --dry-run
    # con il finto LLM degli E2E (avviato a parte su :8766)
    python scripts/e2e/tribunal_eval.py --provider openai --model fake --base-url http://127.0.0.1:8766/v1 --api-key-env NONE
    # contro un provider reale (a pagamento), 3 ripetizioni, report JSON
    OPENAI_API_KEY=... python scripts/e2e/tribunal_eval.py --provider openai --model gpt-4o-mini --repeat 3 --json out.json
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "src" / "backend"
FIXTURE = ROOT / "docs" / "tribunale" / "fixtures" / "seduta-esempio.json"
KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY",
           "openrouter": "OPENROUTER_API_KEY"}
PHASES = ("apertura", "replica", "sintesi")


# ---------------------------------------------------------------------------
# Lettura degli eventi
# ---------------------------------------------------------------------------

def parse_sse(chunks: Iterable[str]) -> list[dict[str, Any]]:
    events = []
    for block in "".join(chunks).split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            try:
                events.append(json.loads(block[len("data: "):]))
            except ValueError:
                pass
    return events


def summarize(events: list[dict[str, Any]], label: str, seconds: float) -> dict[str, Any]:
    """Conteggi per (fase, voce): ammessi, scartati per codice, errore della voce."""
    rows: dict[str, dict[str, Any]] = {}
    outcome = "incompleta"
    for ev in events:
        kind, c = ev.get("type"), ev.get("content") or {}
        if kind == "discarded":
            rows[f"{c['phase']}:{c['voice'] or 'sintesi'}"] = {
                "admitted": c["admitted"], "discarded": c["discarded"], "by_code": c["by_code"], "error": None}
        elif kind == "voice_error":
            rows[f"{c['phase']}:{c['voice']}"] = {"admitted": 0, "discarded": 0, "by_code": {}, "error": c["code"]}
        elif kind == "done":
            outcome = "conclusa"
        elif kind == "error":
            outcome = f"errore {c.get('code')}"
    session = next((e["content"] for e in events if e.get("type") == "session"), {})
    return {"label": label, "outcome": outcome, "seconds": round(seconds, 1), "rows": rows,
            "provider": session.get("provider"), "model": session.get("model"),
            "prompt_version": session.get("prompt_version")}


def print_report(results: list[dict[str, Any]]) -> None:
    total_admitted = total_discarded = 0
    codes: dict[str, int] = defaultdict(int)
    per_voice: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    errors: dict[str, int] = defaultdict(int)
    for res in results:
        print(f"\n== {res['label']}: {res['outcome']} in {res['seconds']} s "
              f"({res['provider']} / {res['model']}, {res['prompt_version']})")
        print(f"   {'fase:voce':<26}{'ammessi':>8}{'scartati':>9}  codici / errore")
        for key in sorted(res["rows"], key=lambda k: (PHASES.index(k.split(':')[0]), k)):
            row = res["rows"][key]
            detail = f"errore {row['error']}" if row["error"] else ", ".join(
                f"{c}:{n}" for c, n in sorted(row["by_code"].items())) or "-"
            print(f"   {key:<26}{row['admitted']:>8}{row['discarded']:>9}  {detail}")
            total_admitted += row["admitted"]
            total_discarded += row["discarded"]
            voice = key.split(":")[1]
            per_voice[voice][0] += row["admitted"]
            per_voice[voice][1] += row["discarded"]
            for code, n in row["by_code"].items():
                codes[code] += n
            if row["error"]:
                errors[f"{key} {row['error']}"] += 1
    print("\n== Totale")
    rate = total_discarded / max(1, total_admitted + total_discarded)
    print(f"   sedute {len(results)}, ammessi {total_admitted}, scartati {total_discarded} ({rate:.0%})")
    for voice, (adm, dis) in sorted(per_voice.items()):
        print(f"   {voice:<14} ammessi {adm:>4}  scartati {dis:>4}")
    for code, n in sorted(codes.items(), key=lambda x: -x[1]):
        print(f"   {code:<26}{n:>5}")
    for err, n in sorted(errors.items()):
        print(f"   errore {err}: {n}")


# ---------------------------------------------------------------------------
# Sorgenti
# ---------------------------------------------------------------------------

def load_case_files(paths: list[str]) -> list[tuple[str, dict[str, Any]]]:
    out = [("seduta-esempio (fixture)", json.loads(FIXTURE.read_text(encoding="utf-8"))["session"]["case_file"])]
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data.get("session"), dict):
            data = data["session"]["case_file"]
        elif isinstance(data.get("case_file"), dict):
            data = data["case_file"]
        out.append((Path(path).name, data))
    return out


def dry_run(case_files: list[tuple[str, dict[str, Any]]], provider: str, model: str) -> None:
    sys.path.insert(0, str(BACKEND))
    from app.services.tribunal import personas

    print(f"Piano (nessuna chiamata): provider={provider} model={model} prompt={personas.PROMPT_VERSION}")
    for label, cf in case_files:
        print(f"\n== {label}: {cf['counts']['total']} fatti ({cf['counts']['citable']} citabili), "
              f"{len(cf['instruments'])} strumenti, scope {cf['scope']['fingerprint']}")
        for voice in personas.VOICE_IDS:
            req = personas.build_opening_request(voice, cf)
            print(f"   apertura:{voice:<14} system {len(req.system_prompt):>6} car.  user "
                  f"{len(req.messages[0]['content']):>6} car.  schema {req.schema_name}")
        for voice in personas.VOICE_IDS:
            req = personas.build_rebuttal_request(voice, cf, [])
            print(f"   replica:{voice:<15} system {len(req.system_prompt):>6} car.  user "
                  f"≥{len(req.messages[0]['content']):>5} car.  schema {req.schema_name}")
        req = personas.build_synthesis_request(cf, [], [])
        print(f"   sintesi:{'sintesi':<15} system {len(req.system_prompt):>6} car.  user "
              f"≥{len(req.messages[0]['content']):>5} car.  schema {req.schema_name}")
        print("   chiamate per seduta: 7 (3 apertura + 3 replica + 1 sintesi, più un nuovo tentativo per "
              "risposta fuori schema)")


def run_in_process(case_files: list[tuple[str, dict[str, Any]]], args: argparse.Namespace) -> list[dict[str, Any]]:
    sys.path.insert(0, str(BACKEND))
    if args.base_url:
        os.environ["OPENAI_BASE_URL"] = args.base_url
    from app.services.doctor_policy.scope import build_scope
    from app.services.tribunal import orchestrator as orch
    from app.services.tribunal.orchestrator import NullSessionStore, TribunalOrchestrator

    key_env = KEY_ENV.get(args.provider, "") if args.api_key_env is None else args.api_key_env
    api_key = os.environ.get(key_env, "") if key_env and key_env != "NONE" else "not-needed"
    if not api_key:
        sys.exit(f"Chiave assente: imposta {key_env} (oppure --dry-run, o --api-key-env NONE con --base-url).")
    settings = SimpleNamespace(
        copilot_provider=args.provider, copilot_model=args.model,
        openai_api_key=api_key if args.provider == "openai" else "",
        anthropic_api_key=api_key if args.provider == "anthropic" else "",
        gemini_api_key=api_key if args.provider == "gemini" else "",
        openrouter_api_key=api_key if args.provider == "openrouter" else "",
        copilot_local_url="", copilot_local_api_key="", copilot_encryption_key="",
        doctor_tribunal_enabled=True, doctor_tribunal_daily_limit=10_000,
        justetf_xray_auto_enrich_enabled_resolved=False,
    )
    repo = SimpleNamespace(get_user_settings=lambda _u: SimpleNamespace(copilot_provider="", copilot_model=""),
                           get_user_copilot_api_key_enc=lambda _u: "")
    results = []
    for label, cf in case_files:
        ids = list(cf["scope"]["portfolio_ids"])
        service = SimpleNamespace(resolve_scope=lambda pids, _u, ids=ids: ids)

        def builder(_repo: Any, _user: str, _ids: Any, cf: dict[str, Any] = cf, **_kw: Any) -> dict[str, Any]:
            out = copy.deepcopy(cf)
            out["scope"] = build_scope(ids).model_dump()
            return out

        for rep in range(args.repeat):
            orchestrator = TribunalOrchestrator(repo, settings, store=NullSessionStore(),
                                                service_getter=lambda s=service: s, case_file_builder=builder)
            started = time.monotonic()
            stream = orchestrator.start("tribunal-eval", ids, force_new=True)
            try:
                events = parse_sse(stream)
            finally:
                orch._LOCKS.release("tribunal-eval")
            results.append(summarize(events, f"{label} #{rep + 1}", time.monotonic() - started))
    return results


def run_backend(args: argparse.Namespace) -> list[dict[str, Any]]:
    results = []
    for scope in args.scope:
        ids = [int(x) for x in scope.split(",") if x.strip()]
        for rep in range(args.repeat):
            body = json.dumps({"portfolio_ids": ids, "force_new": True}).encode()
            req = urllib.request.Request(f"{args.api.rstrip('/')}/doctor/tribunal/sessions", data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            started = time.monotonic()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=300) as resp:
                text = resp.read().decode("utf-8")
            results.append(summarize(parse_sse([text]), f"scope {scope} #{rep + 1}", time.monotonic() - started))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Valutazione del Tribunale: ammessi e scartati per voce e codice.")
    parser.add_argument("--dry-run", action="store_true", help="nessuna chiamata: stampa il piano e i prompt")
    parser.add_argument("--provider", default="openai", choices=sorted(KEY_ENV))
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--api-key-env", default=None, help="variabile con la chiave (NONE = nessuna)")
    parser.add_argument("--base-url", default="", help="OPENAI_BASE_URL (es. finto LLM http://127.0.0.1:8766/v1)")
    parser.add_argument("--case-file", action="append", default=[], help="fascicolo JSON in più (ripetibile)")
    parser.add_argument("--api", default="", help="backend già avviato (es. http://127.0.0.1:8000/api)")
    parser.add_argument("--scope", action="append", default=[], help="con --api: id separati da virgola (ripetibile)")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--json", default="", help="scrive i risultati in questo file")
    args = parser.parse_args()

    if args.api:
        if args.dry_run:
            print(f"Piano (nessuna chiamata): POST {args.api}/doctor/tribunal/sessions con force_new per "
                  f"{args.scope or ['(nessuno scope)']}, {args.repeat} volte; 7 chiamate al modello ciascuna.")
            return
        results = run_backend(args)
    else:
        case_files = load_case_files(args.case_file)
        if args.dry_run:
            dry_run(case_files, args.provider, args.model)
            return
        results = run_in_process(case_files, args)
    print_report(results)
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
