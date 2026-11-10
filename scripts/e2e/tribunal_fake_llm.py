"""LLM finto compatibile OpenAI per il Tribunale del portafoglio (TASK-71).

Nessuna rete, deterministico, solo libreria standard. Il backend gira con
``COPILOT_PROVIDER=openai`` e ``OPENAI_BASE_URL`` verso questo server, così la catena reale
(``copilot.structured.call_structured`` → verificatore → orchestratore → SSE) è esercitata;
solo le «decisioni» del modello sono scritte qui.

Fase e voce si leggono dalla prima riga del prompt di sistema (api-contracts §8.3,
``Tribunale del portafoglio — fase: <fase>; voce: <voce>``); il fascicolo e gli argomenti
verificati si leggono dal messaggio utente, tra ``<fascicolo>`` e ``<argomenti>``. Le
risposte valide citano solo fatti citabili del fascicolo ricevuto, con segnaposto ``{Fn}``.

A comando (stato in ``STATE``, impostabile con ``POST /__state``) il modello produce:

- ``adversarial``: elementi costruiti per rompere il sistema, aggiunti a quelli validi:
  ``numeri`` (cifre e numerali nel testo), ``fatti_inesistenti`` (``F999``, ``{F998}``),
  ``acquisto`` (comprare/vendere/consigliare), ``strumenti`` (ticker, ISIN ed emittente fuori
  dal portafoglio), ``verdetto``, ``id_interni`` (``A-IND-1`` nel testo), ``omoglifi``
  (lettere cirilliche identiche alle latine, accenti combinanti), ``riferimenti``
  (repliche e sintesi verso argomenti inesistenti). Ogni testo avverso contiene la parola
  ``zqxcanary``: se compare negli eventi inviati al frontend il sistema ha fallito.
- ``broken``: ``{"<fase>:<voce>": "json" | "schema" | "empty" | "http500"}`` (``*`` = ogni
  voce, ``sintesi:sintesi`` per la sintesi): JSON non valido negli argomenti del tool,
  JSON valido ma fuori schema, nessuna tool call, errore HTTP del provider.
- ``slow`` / ``delays``: ``{"<fase>:<voce>" | "<voce>" | "*": secondi}``; ``slow`` serve a
  superare il timeout, ``delays`` a far comparire le voci una dopo l'altra (E2E).
- ``credulous``: se il nome di uno strumento contiene un'istruzione (``ignora``,
  ``istruzion``, ``</fascicolo>``…), il modello la «esegue» e aggiunge elementi che la
  seguono (acquisto, numeri inventati, verdetto), marcati con ``zqxinjection``.
- ``only_injection``: con ``credulous``, il modello risponde SOLO con gli elementi iniettati.

Endpoint di servizio: ``GET /__state``, ``POST /__state`` (JSON da fondere nello stato),
``POST /__reset``, ``GET /__calls`` (fase, voce, prima riga del prompt e messaggio utente di
ogni chiamata, per i test). Le richieste che non sono del Tribunale (Copilot) ricevono una
risposta di testo breve.

Uso:
    python scripts/e2e/tribunal_fake_llm.py --port 8766 [--delays indicizzatore=0.4,fattoriale=1.2]
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HEADER_RE = re.compile(r"^Tribunale del portafoglio — fase: (apertura|replica|sintesi); voce: (\w+)\s*$")
CANARY = "zqxcanary"
INJECTION_CANARY = "zqxinjection"
INJECTION_TRIGGERS = ("ignora", "istruzion", "</fascicolo>", "system prompt", "nuove regole")

VOICE_IDS = ("indicizzatore", "fattoriale", "prudente")
VOICE_NAMES = {"indicizzatore": "L'indicizzatore", "fattoriale": "Il fattoriale", "prudente": "Il prudente"}
VOICE_CODES = {"indicizzatore": "IND", "fattoriale": "FAT", "prudente": "PRU"}

# Gruppi di fatti preferiti per voce (il primo fatto citabile di ciascun gruppo).
VOICE_GROUPS = {
    "indicizzatore": ("costi", "concentrazione", "esposizione", "composizione", "salute"),
    "fattoriale": ("esposizione", "composizione", "concentrazione", "scenari", "costi"),
    "prudente": ("stress", "salute", "composizione", "scenari", "concentrazione"),
}
VOICE_STANCES = {
    "indicizzatore": ("punto_di_forza", "criticita", "neutro"),
    "fattoriale": ("punto_di_forza", "neutro", "criticita"),
    "prudente": ("criticita", "criticita", "neutro"),
}
GROUP_THEME = {
    "composizione": "composizione", "concentrazione": "concentrazione", "costi": "costi",
    "salute": "rischio", "esposizione": "esposizione_geografica", "stress": "rischio",
    "scenari": "scenari", "regole": "regole_personali",
}
THEME_PHRASE = {
    "costi": "il costo complessivo del portafoglio",
    "concentrazione": "la concentrazione delle posizioni",
    "composizione": "la composizione per classi di attivo",
    "esposizione_geografica": "l'esposizione per paese e per settore",
    "rischio": "il profilo di rischio",
    "scenari": "la distribuzione degli scenari di lungo periodo",
    "regole_personali": "il rispetto dei parametri personali",
}
VOICE_TEMPLATES = {
    "indicizzatore": "Per chi cerca semplicità e ampia diversificazione conta {phrase}: il dato {ph} è il primo "
                     "elemento da confrontare con un portafoglio globale a basso costo.",
    "fattoriale": "Le inclinazioni volute emergono guardando {phrase}: il dato {ph} mostra dove il portafoglio si "
                  "discosta dal mercato e se la scelta appare consapevole.",
    "prudente": "Per la tenuta nei ribassi pesa {phrase}: il dato {ph} indica quanto il capitale resta esposto "
                "a oscillazioni temporanee del valore.",
}
OPEN_QUESTIONS = (
    "Quanta oscillazione temporanea del valore saresti disposto ad accettare senza cambiare piano?",
    "La concentrazione attuale è una scelta voluta oppure il risultato di decisioni prese in momenti diversi?",
)

_DEFAULT_STATE: dict[str, Any] = {
    "adversarial": [],
    "broken": {},
    "slow": {},
    "delays": {},
    "credulous": False,
    "only_injection": False,
}
STATE: dict[str, Any] = copy.deepcopy(_DEFAULT_STATE)
CALLS: list[dict[str, Any]] = []
_LOCK = threading.Lock()


def reset(**overrides: Any) -> None:
    """Stato iniziale (più ``overrides``) e registro delle chiamate vuoto."""
    with _LOCK:
        STATE.clear()
        STATE.update(copy.deepcopy(_DEFAULT_STATE))
        STATE.update(copy.deepcopy(overrides))
        CALLS.clear()


# ---------------------------------------------------------------------------
# Lettura della richiesta
# ---------------------------------------------------------------------------

def _block(text: str, tag: str) -> dict[str, Any]:
    match = re.search(rf"<{tag}>\n(.*?)\n</{tag}>", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except ValueError:
        return {}


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, list):
        return " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return str(content or "")


def _lookup(table: dict[str, Any], phase: str, voice: str) -> Any:
    for key in (f"{phase}:{voice}", voice, f"{phase}:*", "*"):
        if key in table:
            return table[key]
    return None


# ---------------------------------------------------------------------------
# Risposte valide
# ---------------------------------------------------------------------------

def _citable(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in facts if f.get("citable") and isinstance(f.get("id"), str)]


def _group_of(fact: dict[str, Any]) -> str:
    # Il modello riceve id, label, formatted, unit, quality, citable, reason, subject (non il
    # gruppo): lo si ricava dall'etichetta, come farebbe un lettore.
    label = str(fact.get("label") or "").lower()
    if label.startswith("stress test"):
        return "stress"
    if label.startswith("monte carlo"):
        return "scenari"
    if label.startswith(("tua regola", "regole personali")):
        return "regole"
    if label.startswith("esposizione per") or "look-through" in label or "copertura" in label:
        return "esposizione"
    if label.startswith("ter "):
        return "costi"
    if label.startswith(("peso", "numero di posizioni", "overlap")):
        return "concentrazione"
    if label.startswith("quota"):
        return "composizione"
    return "salute"


def _pick_facts(voice: str, facts: list[dict[str, Any]], count: int = 3) -> list[dict[str, Any]]:
    citable = _citable(facts)
    chosen: list[dict[str, Any]] = []
    for group in VOICE_GROUPS[voice]:
        for fact in citable:
            if _group_of(fact) == group and fact not in chosen:
                chosen.append(fact)
                break
        if len(chosen) == count:
            return chosen
    for fact in citable:
        if len(chosen) == count:
            break
        if fact not in chosen:
            chosen.append(fact)
    return chosen


def valid_opening(voice: str, case_file: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for index, fact in enumerate(_pick_facts(voice, case_file.get("facts") or [])):
        theme = GROUP_THEME.get(_group_of(fact), "composizione")
        text = VOICE_TEMPLATES[voice].format(phrase=THEME_PHRASE[theme], ph="{" + fact["id"] + "}")
        out.append({"theme": theme, "stance": VOICE_STANCES[voice][index % 3], "text": text,
                    "fact_ids": [fact["id"]]})
    return out


def valid_rebuttals(voice: str, arguments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen: set[str] = set()
    for arg in arguments:
        other = arg.get("voice")
        if other == voice or other in seen or not arg.get("fact_ids"):
            continue
        seen.add(other)
        fid = arg["fact_ids"][0]
        stance = "contesta" if not out else "precisa"
        text = (f"{VOICE_NAMES[voice]} legge il dato {{{fid}}} in un altro modo: va pesato insieme al resto "
                "del fascicolo, senza trarne conclusioni affrettate.")
        out.append({"target_argument_id": arg["id"], "stance": stance, "text": text, "fact_ids": [fid]})
        if len(out) == 2:
            break
    return out


def valid_synthesis(arguments: list[dict[str, Any]], rebuttals: list[dict[str, Any]]) -> dict[str, Any]:
    by_voice: dict[str, list[dict[str, Any]]] = {}
    for arg in arguments:
        by_voice.setdefault(arg.get("voice"), []).append(arg)
    voices = [v for v in VOICE_IDS if by_voice.get(v)]
    shared: list[dict[str, Any]] = []
    contested: list[dict[str, Any]] = []
    if len(voices) >= 2:
        a1, a2 = by_voice[voices[0]][0], by_voice[voices[1]][0]
        f1 = a1["fact_ids"][0]
        shared.append({
            "text": f"Le voci concordano nel considerare centrale il dato {{{f1}}}, che torna in più letture "
                    "del portafoglio.",
            "fact_ids": [f1], "argument_ids": [a1["id"], a2["id"]],
        })
        left = by_voice[voices[0]][-1]
        right = by_voice[voices[-1]][-1]
        fl, fr = left["fact_ids"][0], right["fact_ids"][0]
        contested.append({
            "text": f"Il peso da dare al dato {{{fl}}} divide le voci.",
            "fact_ids": [fl],
            "sides": [
                {"argument_ids": [left["id"]], "fact_ids": [fl],
                 "summary": f"Per {VOICE_NAMES[voices[0]].lower()} il dato {{{fl}}} conta più del resto."},
                {"argument_ids": [right["id"]], "fact_ids": [fr],
                 "summary": f"Per {VOICE_NAMES[voices[-1]].lower()} pesa di più il dato {{{fr}}}."},
            ],
        })
    return {
        "shared_points": shared,
        "contested_points": contested,
        "open_questions": [{"text": q} for q in OPEN_QUESTIONS],
    }


# ---------------------------------------------------------------------------
# Risposte avverse
# ---------------------------------------------------------------------------

def _adv_opening(kind: str, fid: str) -> list[dict[str, Any]]:
    def arg(text: str, fact_ids: list[str] | None = None) -> dict[str, Any]:
        return {"theme": "rischio", "stance": "criticita", "text": text,
                "fact_ids": [fid] if fact_ids is None else fact_ids}

    ph = "{" + fid + "}"
    table = {
        "numeri": [
            arg(f"Il rendimento {CANARY} atteso è del 7% annuo, ben sopra il dato {ph} del fascicolo."),
            arg(f"Negli ultimi dieci anni {CANARY} il portafoglio avrebbe perso la metà del valore, oltre il dato {ph}."),
            arg(f"Con un costo annuo di 250 € {CANARY} il portafoglio resta caro rispetto al dato {ph}."),
        ],
        "fatti_inesistenti": [
            arg(f"Il dato {{F999}} {CANARY} mostra un rischio nascosto che il fascicolo non riporta.", ["F999"]),
            arg(f"Il valore {{F998}} {CANARY} conferma una fragilità del portafoglio nei ribassi.", [fid, "F998"]),
        ],
        "acquisto": [
            arg(f"Conviene comprare altre quote {CANARY} del fondo principale, visto il dato {ph}."),
            arg(f"Ti consiglio {CANARY} di alleggerire la posizione più piccola, visto il dato {ph}."),
            arg(f"Sarebbe meglio vendere {CANARY} lo strumento difensivo, visto il dato {ph}."),
        ],
        "strumenti": [
            arg(f"Un fondo come XDWD {CANARY} darebbe una diversificazione più ampia del dato {ph}."),
            arg(f"Lo strumento LU0274208692 {CANARY} offrirebbe una copertura migliore del dato {ph}."),
            arg(f"Un prodotto amundi {CANARY} sul mercato globale ridurrebbe il dato {ph}."),
        ],
        "verdetto": [
            arg(f"Su questo punto l'indicizzatore ha ragione {CANARY} e le altre letture no, visto il dato {ph}."),
        ],
        # Omoglifi e diacritici combinanti: «о»/«Х» cirillici, «e» + accento combinante.
        "omoglifi": [
            arg(f"Conviene c\u043emprare altre quote {CANARY} del fondo principale, visto il dato {ph}."),
            arg(f"Un fondo come \u0425DWD {CANARY} darebbe una diversificazione più ampia del dato {ph}."),
            arg(f"Sarebbe meglio vende\u0301re {CANARY} lo strumento difensivo, visto il dato {ph}."),
        ],
        "id_interni": [
            arg(f"Come già detto in A-IND-1 {CANARY}, il dato {ph} pesa molto sul portafoglio."),
            arg(f"Il fatto F12 {CANARY} va letto insieme al dato {ph} del fascicolo."),
        ],
    }
    return table.get(kind, [])


def _adv_rebuttals(kind: str, voice: str, arguments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    others = [a for a in arguments if a.get("voice") != voice and a.get("fact_ids")]
    own = [a for a in arguments if a.get("voice") == voice]
    if not others:
        return []
    target, fid = others[0]["id"], others[0]["fact_ids"][0]
    ph = "{" + fid + "}"

    def reb(text: str, target_id: str = target, fact_ids: list[str] | None = None) -> dict[str, Any]:
        return {"target_argument_id": target_id, "stance": "contesta", "text": text,
                "fact_ids": [fid] if fact_ids is None else fact_ids}

    table = {
        "numeri": [reb(f"Il dato {ph} {CANARY} sottovaluta un rischio del 12% che il fascicolo ignora.")],
        "fatti_inesistenti": [reb(f"Il dato {{F997}} {CANARY} smentisce questa lettura del portafoglio.", fact_ids=["F997"])],
        "acquisto": [reb(f"Il dato {ph} {CANARY} suggerisce di vendere subito la posizione principale.")],
        "strumenti": [reb(f"Il dato {ph} {CANARY} si risolverebbe con un fondo come CSPX quotato altrove.")],
        "verdetto": [reb(f"Il dato {ph} {CANARY} dimostra che questa voce è la perdente della seduta.")],
        "omoglifi": [reb(f"Il dato {ph} {CANARY} suggerisce di v\u0435ndere subito la posizione principale.")],
        "id_interni": [reb(f"Il dato {ph} {CANARY} contraddice R-FAT-1 della replica precedente.")],
        "riferimenti": [
            reb(f"Il dato {ph} {CANARY} contraddice un argomento che nessuno ha scritto.", target_id="A-IND-9"),
            *([reb(f"Il dato {ph} {CANARY} conferma la lettura che questa voce ha già dato.", target_id=own[0]["id"])]
              if own else []),
        ],
    }
    return table.get(kind, [])


def _adv_synthesis(kind: str, arguments: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_voice: dict[str, dict[str, Any]] = {}
    for arg in arguments:
        by_voice.setdefault(arg.get("voice"), arg)
    firsts = [by_voice[v] for v in VOICE_IDS if v in by_voice]
    if len(firsts) < 2:
        return {}
    a1, a2 = firsts[0], firsts[1]
    f1, f2 = a1["fact_ids"][0], a2["fact_ids"][0]
    ids = [a1["id"], a2["id"]]

    def shared(text: str, fact_ids: list[str] | None = None, argument_ids: list[str] | None = None) -> dict[str, Any]:
        return {"text": text, "fact_ids": [f1] if fact_ids is None else fact_ids,
                "argument_ids": ids if argument_ids is None else argument_ids}

    def contested(side_text: str) -> dict[str, Any]:
        return {"text": f"Il peso del dato {{{f1}}} divide le voci {CANARY} in modo netto.", "fact_ids": [f1],
                "sides": [{"argument_ids": [a1["id"]], "fact_ids": [f1], "summary": side_text},
                          {"argument_ids": [a2["id"]], "fact_ids": [f2],
                           "summary": f"Per l'altra voce pesa di più il dato {{{f2}}}."}]}

    table = {
        "numeri": {"shared_points": [shared(f"Le voci concordano {CANARY} che il portafoglio renderà il 5% annuo, oltre il dato {{{f1}}}.")],
                   "open_questions": [{"text": f"Accetteresti {CANARY} una perdita del 30% in un anno?"}]},
        "fatti_inesistenti": {"shared_points": [shared(f"Le voci concordano {CANARY} sul dato {{F996}}, che il fascicolo non contiene.", ["F996"])]},
        "acquisto": {"contested_points": [contested(f"Per una voce {CANARY} conviene comprare altre quote, visto il dato {{{f1}}}.")],
                     "open_questions": [{"text": f"Vuoi {CANARY} che ti consigli un fondo migliore di quelli che hai?"}]},
        "strumenti": {"contested_points": [contested(f"Per una voce {CANARY} un fondo come XDWD coprirebbe meglio il dato {{{f1}}}.")]},
        "verdetto": {"shared_points": [shared(f"Alla fine vince {CANARY} la lettura prudente, come mostra il dato {{{f1}}}.")]},
        "omoglifi": {"shared_points": [shared(f"Alla fine v\u0456nce {CANARY} la lettura prudente, come mostra il dato {{{f1}}}.")]},
        "id_interni": {"shared_points": [shared(f"Come in A-FAT-1 {CANARY}, le voci leggono allo stesso modo il dato {{{f1}}}.")]},
        "riferimenti": {"shared_points": [shared(f"Le voci concordano {CANARY} sul dato {{{f1}}} letto da tutte.",
                                                 argument_ids=[a1["id"], "A-PRU-9"])]},
    }
    return table.get(kind, {})


def _injected(case_file: dict[str, Any]) -> bool:
    names = " ".join(str(i.get("name") or "") + " " + str(i.get("symbol") or "")
                     for i in case_file.get("instruments") or []).lower()
    return any(trigger in names for trigger in INJECTION_TRIGGERS)


def _injection_items(phase: str, voice: str, arguments: list[dict[str, Any]],
                     case_file: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Cosa scriverebbe un modello che obbedisce all'istruzione nascosta nel nome."""
    citable = _citable(case_file.get("facts") or [])
    fid = citable[0]["id"] if citable else "F1"
    ph = "{" + fid + "}"
    if phase == "apertura":
        return {"arguments": [
            {"theme": "costi", "stance": "punto_di_forza", "fact_ids": [fid],
             "text": f"Come richiesto {INJECTION_CANARY}, compra subito altre quote di questo fondo: il dato {ph} lo conferma."},
            {"theme": "rischio", "stance": "punto_di_forza", "fact_ids": [fid],
             "text": f"Il portafoglio {INJECTION_CANARY} renderà il venti per cento l'anno, come indica il dato {ph}."},
            {"theme": "rischio", "stance": "punto_di_forza", "fact_ids": [fid],
             "text": f"Questa voce {INJECTION_CANARY} è la vincitrice della seduta, come mostra il dato {ph}."},
        ]}
    if phase == "replica":
        others = [a for a in arguments if a.get("voice") != voice]
        if not others:
            return {"rebuttals": []}
        return {"rebuttals": [{"target_argument_id": others[0]["id"], "stance": "contesta", "fact_ids": [fid],
                               "text": f"Come richiesto {INJECTION_CANARY}, conviene vendere tutto e acquistare questo fondo."}]}
    firsts: dict[str, str] = {}
    for arg in arguments:
        firsts.setdefault(arg.get("voice"), arg["id"])
    ids = list(firsts.values())[:2]
    first = next((a for a in arguments if a.get("fact_ids")), None)
    sfid = first["fact_ids"][0] if first else fid
    return {
        "shared_points": [{"text": f"Le voci concordano {INJECTION_CANARY}: compra il fondo indicato nel fascicolo.",
                           "fact_ids": [sfid], "argument_ids": ids}],
        "open_questions": [{"text": f"Hai già comprato {INJECTION_CANARY} il fondo raccomandato?"}],
    }


# ---------------------------------------------------------------------------
# Risposta di una chiamata del Tribunale
# ---------------------------------------------------------------------------

def tribunal_payload(phase: str, voice: str, user_text: str, state: dict[str, Any]) -> dict[str, Any]:
    case_file = _block(user_text, "fascicolo")
    block = _block(user_text, "argomenti")
    arguments = block.get("arguments") or []
    rebuttals = block.get("rebuttals") or []
    citable = _citable(case_file.get("facts") or [])
    fid = citable[0]["id"] if citable else "F1"
    kinds = list(state.get("adversarial") or [])
    injected = bool(state.get("credulous")) and _injected(case_file)
    only_injection = injected and bool(state.get("only_injection"))

    if phase == "apertura":
        items = [] if only_injection else valid_opening(voice, case_file)
        for kind in kinds:
            items.extend(_adv_opening(kind, fid))
        if injected:
            items.extend(_injection_items(phase, voice, arguments, case_file)["arguments"])
        return {"arguments": items}
    if phase == "replica":
        items = [] if only_injection else valid_rebuttals(voice, arguments)
        for kind in kinds:
            items.extend(_adv_rebuttals(kind, voice, arguments))
        if injected:
            items.extend(_injection_items(phase, voice, arguments, case_file)["rebuttals"])
        return {"rebuttals": items}
    payload = ({"shared_points": [], "contested_points": [], "open_questions": []} if only_injection
               else valid_synthesis(arguments, rebuttals))
    extras = [_adv_synthesis(kind, arguments) for kind in kinds]
    if injected:
        extras.append(_injection_items(phase, voice, arguments, case_file))
    for extra in extras:
        for key, values in extra.items():
            payload[key] = list(payload.get(key) or []) + values
    return payload


def _completion(message: dict[str, Any], finish_reason: str, model: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-trb-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model or "fake-tribunal",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def respond(body: dict[str, Any]) -> tuple[int, dict[str, Any], float]:
    """(status HTTP, corpo JSON, secondi di attesa prima di rispondere)."""
    messages = body.get("messages") or []
    system = next((_message_text(m) for m in messages if m.get("role") == "system"), "")
    user = next((_message_text(m) for m in reversed(messages) if m.get("role") == "user"), "")
    model = str(body.get("model") or "")
    match = HEADER_RE.match(system.splitlines()[0] if system else "")
    if not match:
        return 200, _completion({"role": "assistant", "content": "Risposta di prova del Copilot (LLM finto)."},
                                "stop", model), 0.0
    phase, voice = match.group(1), match.group(2)
    with _LOCK:
        state = copy.deepcopy(STATE)
        CALLS.append({"phase": phase, "voice": voice, "header": system.splitlines()[0], "system": system,
                      "user": user, "tool": ((body.get("tool_choice") or {}).get("function") or {}).get("name")})
    wait_s = float(_lookup(state.get("delays") or {}, phase, voice) or 0) + float(
        _lookup(state.get("slow") or {}, phase, voice) or 0)
    tool_name = ((body.get("tool_choice") or {}).get("function") or {}).get("name") or "tribunal"
    broken = _lookup(state.get("broken") or {}, phase, voice)
    if broken == "http500":
        return 500, {"error": {"message": "fake provider failure", "type": "server_error"}}, wait_s
    if broken == "empty":
        return 200, _completion({"role": "assistant", "content": f"Ecco la risposta {CANARY} senza strumento."},
                                "stop", model), wait_s
    if broken == "json":
        arguments = '{"arguments": [{"theme": "costi", "text": "' + CANARY + ' il portafoglio rende il 9%"'
    elif broken == "schema":
        # Il valore fuori schema contiene il testo del modello: non deve finire nemmeno nei log.
        key = {"apertura": "arguments", "replica": "rebuttals"}.get(phase, "shared_points")
        arguments = json.dumps({key: f"{CANARY} compra tutto, rende il 9%"})
    else:
        arguments = json.dumps(tribunal_payload(phase, voice, user, state), ensure_ascii=False)
    message = {"role": "assistant", "content": None, "tool_calls": [{
        "id": f"call_{phase}_{voice}", "type": "function",
        "function": {"name": tool_name, "arguments": arguments},
    }]}
    return 200, _completion(message, "tool_calls", model), wait_s


# ---------------------------------------------------------------------------
# Server HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # silenzioso
        pass

    def _send(self, status: int, payload: Any, content_type: str = "application/json") -> None:
        raw = (payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):  # il client ha abbandonato (timeout)
            pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/__state"):
            with _LOCK:
                self._send(200, STATE)
            return
        if self.path.startswith("/__calls"):
            with _LOCK:
                self._send(200, [{k: c[k] for k in ("phase", "voice", "header", "tool")} for c in CALLS])
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if self.path.startswith("/__reset"):
            reset(**(json.loads(raw) if raw.strip() else {}))
            self._send(200, STATE)
            return
        if self.path.startswith("/__state"):
            with _LOCK:
                STATE.update(json.loads(raw or b"{}"))
                self._send(200, STATE)
            return
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send(404, {"error": {"message": "not found"}})
            return
        body = json.loads(raw or b"{}")
        status, payload, wait_s = respond(body)
        if wait_s > 0:
            time.sleep(wait_s)
        if body.get("stream") and status == 200:
            content = payload["choices"][0]["message"].get("content") or ""
            chunk = {"id": payload["id"], "object": "chat.completion.chunk", "created": payload["created"],
                     "model": payload["model"],
                     "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}]}
            end = {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            self._send(200, f"data: {json.dumps(chunk)}\n\ndata: {json.dumps(end)}\n\ndata: [DONE]\n\n",
                       "text/event-stream")
            return
        self._send(status, payload)


def serve(port: int = 0, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Server non ancora avviato (``serve_forever`` in un thread per i test)."""
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def _parse_delays(value: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in filter(None, (p.strip() for p in value.split(","))):
        key, _, seconds = part.partition("=")
        out[key.strip()] = float(seconds)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--delays", default="", help="es. indicizzatore=0.4,fattoriale=1.2,prudente=2")
    parser.add_argument("--adversarial", default="", help="tipi avversi separati da virgola")
    args = parser.parse_args()
    reset(delays=_parse_delays(args.delays),
          adversarial=[k for k in args.adversarial.split(",") if k])
    serve(args.port).serve_forever()


if __name__ == "__main__":
    main()
