#!/usr/bin/env python3
"""Chiama un tool del server MCP di Valore365 sui portafogli di prova dell'Auditor (TASK-82).

In processo, senza login Clerk e senza server HTTP: stessa ``run_tool_sync`` e stesse dipendenze
del server MCP (``build_tool_dependencies(offline=True)``: nessun provider esterno), come utente
``auditor-seed-user``. Il risultato è ripulito con ``sanitize_output`` come lo vede un client MCP e
stampato come JSON su stdout.

    python3 scripts/auditor/mcp_call.py list_portfolios '{}'
    python3 scripts/auditor/mcp_call.py get_cost_breakdown '{"portfolio_id": 9103}'
    python3 scripts/auditor/mcp_call.py get_stress_test '{"portfolio_id": 9101}' --save /tmp/x/stress.json
    python3 scripts/auditor/mcp_call.py --list              # tool esposti e parametri
    python3 scripts/auditor/mcp_call.py --schema get_monte_carlo   # schema JSON completo di un tool
    python3 scripts/auditor/mcp_call.py --batch calls.jsonl  # una chiamata per riga: {"tool": ..., "args": {...}}

Database: ``--database-url``, altrimenti ``$DATABASE_URL``, altrimenti il file
``$AGENT_DIR/database_url`` scritto da ``scripts/auditor/agent_stack.sh start``
(default ``/tmp/valore365-auditor-agent``). Sono ammessi solo database locali (socket Unix,
``localhost``, ``127.0.0.1``, ``::1``): lo script rifiuta qualunque altro host, così non può
leggere dati di produzione. Durante la chiamata le connessioni di rete non locali sono bloccate.

Codici di uscita: 0 risultato stampato; 1 il tool ha risposto con un errore (stampato come
``{"error": "..."}``, lo stesso messaggio che riceverebbe un client MCP); 2 errore d'uso o di
configurazione (argomenti non JSON, database non locale o non raggiungibile).

Ogni chiamata viene registrata (tool, argomenti, esito, durata; mai l'output) in
``$MCP_CALL_LOG`` (default ``$AGENT_DIR/mcp_calls.jsonl`` se la cartella esiste): serve a contare
le chiamate della sessione per il report e per il budget del playbook.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "src" / "backend"
DEFAULT_USER = "auditor-seed-user"
AGENT_DIR = Path(os.environ.get("AGENT_DIR", "/tmp/valore365-auditor-agent"))
LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}

EXIT_OK, EXIT_TOOL_ERROR, EXIT_USAGE = 0, 1, 2


class UsageError(Exception):
    pass


def _resolve_database_url(explicit: str | None) -> str:
    url = explicit or os.environ.get("DATABASE_URL")
    if not url:
        stored = AGENT_DIR / "database_url"
        if stored.is_file():
            url = stored.read_text(encoding="utf-8").strip()
    if not url:
        raise UsageError(
            "DATABASE_URL non impostato: avviare lo stack con scripts/auditor/agent_stack.sh start "
            "oppure passare --database-url")
    parts = urlsplit(url)
    hosts = [parts.hostname or ""] + parse_qs(parts.query).get("host", [])
    for host in hosts:
        if host.startswith("/"):
            continue  # socket Unix locale
        if host.lower() not in LOCAL_HOSTS:
            raise UsageError(f"database non locale rifiutato (host {host!r}): solo lo stack dell'Auditor")
    return url


def _block_network() -> None:
    real_connect = socket.socket.connect

    def _connect(sock: socket.socket, address: Any) -> Any:
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0] if isinstance(address, tuple) else str(address)
            if host not in ("127.0.0.1", "::1", "localhost"):
                raise ConnectionRefusedError(f"rete non ammessa da mcp_call.py: {address!r}")
        return real_connect(sock, address)

    socket.socket.connect = _connect  # type: ignore[method-assign]


def _prepare_environment(database_url: str) -> None:
    """Prima di importare l'app: impostazioni lette da get_settings() alla prima importazione."""
    os.environ["DATABASE_URL"] = database_url
    os.environ.setdefault("APP_ENV", "dev")
    os.environ.setdefault("CLERK_AUTH_ENABLED", "false")
    os.environ.setdefault("JUSTETF_ENABLED", "false")
    os.environ.setdefault("JUSTETF_XRAY_AUTO_ENRICH_ENABLED", "false")
    os.environ.setdefault("FINANCE_MAX_RETRIES", "0")
    os.environ.setdefault("FINANCE_REQUEST_TIMEOUT_SECONDS", "2")
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))


def _load_deps():
    from app.services.auditor.context import build_tool_dependencies
    import app.services.doctor_policy.service as doctor_service

    deps = build_tool_dependencies(offline=True)
    # Il servizio del Doctor è un singleton di processo: legato esplicitamente allo stesso repository
    # (architecture.md, Deviazioni TASK-78).
    doctor_service._default_service = doctor_service.DoctorPolicyService(deps.repo)
    return deps


def _call_log_path() -> Path | None:
    explicit = os.environ.get("MCP_CALL_LOG")
    if explicit:
        return Path(explicit)
    return AGENT_DIR / "mcp_calls.jsonl" if AGENT_DIR.is_dir() else None


def _log_call(tool: str, args: dict[str, Any], ok: bool, duration_ms: float, error: str | None) -> None:
    path = _call_log_path()
    if path is None:
        return
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tool": tool, "args": args, "ok": ok,
             "duration_ms": round(duration_ms), "error": error}
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def call_tool(deps: Any, tool: str, args: dict[str, Any], user_id: str) -> tuple[bool, Any]:
    """(ok, risultato ripulito) oppure (False, {"error": messaggio}) come lo vedrebbe un client MCP."""
    from app.mcp_server.tools import McpToolError, run_tool_sync, sanitize_output, serialize_result

    started = time.monotonic()
    try:
        result = sanitize_output(run_tool_sync(deps, tool, dict(args), user_id))
    except McpToolError as exc:
        payload: Any = {"error": str(exc)}
        ok = False
    except Exception as exc:  # noqa: BLE001 - come il server: messaggio generico, dettaglio nei log
        logging.getLogger("mcp_call").debug("tool %s fallito", tool, exc_info=True)
        payload = {"error": f"Errore nell'esecuzione del tool {tool}", "exception": type(exc).__name__}
        ok = False
    else:
        _, truncated = serialize_result(result)
        if truncated:
            print(f"mcp_call: attenzione, un client MCP riceverebbe l'output troncato a 200 KB ({tool})",
                  file=sys.stderr)
        payload, ok = result, True
    _log_call(tool, args, ok, (time.monotonic() - started) * 1000, None if ok else payload.get("error"))
    return ok, payload


def _parse_args_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsageError(f"argomenti non JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise UsageError("gli argomenti devono essere un oggetto JSON")
    return value


def _describe_param(name: str, prop: dict[str, Any], required: set[str]) -> str:
    kind = prop.get("type") or ("enum" if "enum" in prop else "any")
    if isinstance(kind, list):
        kind = "|".join(str(k) for k in kind)
    if "enum" in prop:
        kind = "|".join(json.dumps(v, ensure_ascii=False) for v in prop["enum"])
    elif kind == "array" and isinstance(prop.get("items"), dict):
        kind = f"array<{prop['items'].get('type', 'object')}>"
    bounds = [f"{key}={prop[key]}" for key in ("minimum", "maximum", "minItems", "maxItems") if key in prop]
    text = f"{name}{'' if name in required else '?'}: {kind}"
    return text + (f" [{', '.join(bounds)}]" if bounds else "")


def list_tools(as_json: bool) -> None:
    from app.mcp_server.tools import build_tool_list

    tools = build_tool_list()
    if as_json:
        print(json.dumps([{"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                          for t in tools], ensure_ascii=False, indent=2))
        return
    for tool in sorted(tools, key=lambda t: t.name):
        schema = tool.inputSchema or {}
        required = set(schema.get("required") or [])
        params = [_describe_param(n, p, required) for n, p in (schema.get("properties") or {}).items()]
        summary = (tool.description or "").split(". ")[0].strip()
        print(f"{tool.name}({', '.join(params)})")
        print(f"    {summary[:200]}")


def print_schema(name: str) -> int:
    from app.mcp_server.tools import build_tool_list

    for tool in build_tool_list():
        if tool.name == name:
            print(json.dumps({"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema},
                             ensure_ascii=False, indent=2))
            return EXIT_OK
    print(f"mcp_call: tool sconosciuto {name!r} (vedi --list)", file=sys.stderr)
    return EXIT_USAGE


def run_batch(deps: Any, path: str, user_id: str) -> int:
    source = sys.stdin if path == "-" else open(path, encoding="utf-8")  # noqa: SIM115
    worst = EXIT_OK
    with source:
        for lineno, line in enumerate(source, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                item = json.loads(line)
                tool, args = item["tool"], item.get("args") or {}
                if not isinstance(args, dict):
                    raise TypeError("args non è un oggetto")
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise UsageError(f"{path}:{lineno}: riga non valida ({exc})") from exc
            ok, payload = call_tool(deps, tool, args, user_id)
            out = {"tool": tool, "args": args, "ok": ok, "result": payload}
            if "label" in item:
                out["label"] = item["label"]
            print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
            if not ok:
                worst = EXIT_TOOL_ERROR
    return worst


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp_call.py",
        description="Chiama un tool MCP di Valore365 sui portafogli di prova dell'Auditor (in processo, offline).")
    parser.add_argument("tool", nargs="?", help="nome del tool (vedi --list)")
    parser.add_argument("args", nargs="?", default="{}", help="argomenti come oggetto JSON (default {})")
    parser.add_argument("--user", default=DEFAULT_USER, help=f"utente proprietario (default {DEFAULT_USER})")
    parser.add_argument("--database-url", help="default: $DATABASE_URL o $AGENT_DIR/database_url")
    parser.add_argument("--list", action="store_true", help="elenca i tool esposti con i parametri ed esce")
    parser.add_argument("--json", action="store_true", help="con --list: schemi completi in JSON")
    parser.add_argument("--schema", metavar="TOOL", help="stampa lo schema degli argomenti di un tool ed esce")
    parser.add_argument("--batch", metavar="FILE", help="file JSONL ({\"tool\", \"args\"} per riga, - = stdin); "
                        "stampa una riga JSON per chiamata")
    parser.add_argument("--compact", action="store_true", help="JSON su una riga invece che indentato")
    parser.add_argument("--save", metavar="PATH", help="salva anche il risultato in un file JSON")
    parser.add_argument("--debug", action="store_true", help="log dell'app su stderr (eccezioni dei tool)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.ERROR, stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.list or args.schema:
            # Nessun database necessario: gli schemi vengono dalle definizioni dei tool.
            _prepare_environment(os.environ.get("DATABASE_URL") or "postgresql+psycopg://postgres@/none?host=/nonexistent")
            return print_schema(args.schema) if args.schema else (list_tools(args.json) or EXIT_OK)
        if not args.tool and not args.batch:
            raise UsageError("indicare un tool (o --list, --schema, --batch)")
        tool_args = _parse_args_json(args.args) if args.tool else {}
        database_url = _resolve_database_url(args.database_url)
        _prepare_environment(database_url)
        _block_network()
        try:
            deps = _load_deps()
        except Exception as exc:  # noqa: BLE001
            raise UsageError(f"dipendenze non disponibili: {type(exc).__name__}: {exc}") from exc
        if args.batch:
            return run_batch(deps, args.batch, args.user)
        ok, payload = call_tool(deps, args.tool, tool_args, args.user)
    except UsageError as exc:
        print(f"mcp_call: {exc}", file=sys.stderr)
        return EXIT_USAGE
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":") if args.compact else None,
                      indent=None if args.compact else 2)
    print(text)
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(text + "\n", encoding="utf-8")
    return EXIT_OK if ok else EXIT_TOOL_ERROR


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # es. "mcp_call.py --list | head"
        sys.stderr.close()
        sys.exit(EXIT_OK)
