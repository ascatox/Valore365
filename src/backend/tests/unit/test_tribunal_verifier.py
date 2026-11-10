"""Tests for the Tribunale verifier (TASK-64, docs/tribunale/api-contracts.md §7)."""

from __future__ import annotations

import copy
import json
import socket
from pathlib import Path
from typing import Any

import pytest

from app.services.tribunal import verifier as v

FIXTURE = Path(__file__).resolve().parents[4] / "docs/tribunale/fixtures" / "seduta-esempio.json"


@pytest.fixture(scope="module")
def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def case_file(fixture: dict[str, Any]) -> dict[str, Any]:
    return fixture["session"]["case_file"]


@pytest.fixture(scope="module")
def session(fixture: dict[str, Any]) -> dict[str, Any]:
    return fixture["session"]


def _run_fixture(fixture: dict[str, Any]):
    cf = fixture["session"]["case_file"]
    raw = fixture["raw"]
    arguments, rebuttals, discards, summaries = [], [], [], []
    for voice in v.VOICE_ORDER:
        res = v.verify_opening(voice, raw["apertura"][voice], cf)
        arguments += res.admitted
        discards += [("apertura", voice, d.path, d.code) for d in res.discarded]
        summaries.append({"phase": "apertura", "voice": voice, "admitted": len(res.admitted),
                          "discarded": len(res.discarded), "by_code": res.by_code()})
    for voice in v.VOICE_ORDER:
        res = v.verify_rebuttals(voice, raw["replica"][voice], cf, arguments)
        rebuttals += res.admitted
        discards += [("replica", voice, d.path, d.code) for d in res.discarded]
        summaries.append({"phase": "replica", "voice": voice, "admitted": len(res.admitted),
                          "discarded": len(res.discarded), "by_code": res.by_code()})
    syn = v.verify_synthesis(raw["sintesi"], cf, arguments, rebuttals)
    discards += [("sintesi", None, d.path, d.code) for d in syn.discarded]
    summaries.append({"phase": "sintesi", "voice": None, "admitted": syn.admitted_count,
                      "discarded": len(syn.discarded), "by_code": syn.by_code()})
    return arguments, rebuttals, syn, discards, summaries


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def test_fixture_exists() -> None:
    assert FIXTURE.is_file(), FIXTURE


def test_fixture_admitted_items_match_session(fixture: dict[str, Any], session: dict[str, Any]) -> None:
    arguments, rebuttals, syn, _discards, _summaries = _run_fixture(fixture)
    assert arguments == session["arguments"]
    assert rebuttals == session["rebuttals"]
    assert syn.synthesis == session["synthesis"]
    # final texts identical, one by one (explicit, for readability of failures)
    for got, want in zip(arguments, session["arguments"]):
        assert got["text"] == want["text"]


def test_fixture_discards_match_expected(fixture: dict[str, Any]) -> None:
    *_rest, discards, _summaries = _run_fixture(fixture)
    expected = [(e["phase"], e["voice"], e["path"], e["code"]) for e in fixture["expected_discards"]]
    assert discards == expected
    assert len(discards) == 7


def test_fixture_discard_summaries_match_session(fixture: dict[str, Any], session: dict[str, Any]) -> None:
    *_rest, summaries = _run_fixture(fixture)
    assert summaries == session["discarded"]


def test_fixture_is_deterministic_and_inputs_untouched(fixture: dict[str, Any]) -> None:
    before = copy.deepcopy(fixture)
    first = _run_fixture(fixture)
    second = _run_fixture(fixture)
    assert first[0] == second[0] and first[1] == second[1]
    assert first[2].synthesis == second[2].synthesis
    assert first[3] == second[3]
    assert fixture == before


def test_no_network_access(fixture: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("network access")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    _run_fixture(fixture)


# ---------------------------------------------------------------------------
# Helpers for single-item cases
# ---------------------------------------------------------------------------

OK_TEXT = "Il TER medio ponderato è {F9}, un livello coerente con una gestione passiva."


def arg(text: str = OK_TEXT, fact_ids: Any = None, **extra: Any) -> dict[str, Any]:
    item = {"theme": "costi", "stance": "punto_di_forza", "text": text,
            "fact_ids": ["F9"] if fact_ids is None else fact_ids}
    item.update(extra)
    return item


def opening_code(case_file: dict[str, Any], item: Any) -> str | None:
    res = v.verify_opening("indicizzatore", {"arguments": [item]}, case_file)
    if res.admitted:
        return None
    assert len(res.discarded) == 1 and res.discarded[0].path == "arguments[0]"
    return res.discarded[0].code


def opening_admitted(case_file: dict[str, Any], item: Any) -> dict[str, Any]:
    res = v.verify_opening("indicizzatore", {"arguments": [item]}, case_file)
    assert res.discarded == [], res.discarded
    return res.admitted[0]


@pytest.fixture(scope="module")
def admitted_args(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return fixture["session"]["arguments"]


@pytest.fixture(scope="module")
def admitted_rebs(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return fixture["session"]["rebuttals"]


def test_discard_codes_order() -> None:
    assert v.DISCARD_CODES == (
        "schema_non_valido", "riferimento_non_ammesso", "nessun_fatto", "troppi_fatti",
        "fatto_inesistente", "fatto_non_citabile", "segnaposto_malformato",
        "segnaposto_non_citato", "fatto_estraneo", "testo_troppo_lungo",
        "strumento_non_ammesso", "cifra_libera", "indicazione_operativa", "verdetto",
        "troppi_argomenti",
    )


def test_constants() -> None:
    assert (v.MAX_ARGUMENTS_PER_VOICE, v.MAX_REBUTTALS_PER_VOICE, v.MAX_FACTS_PER_ITEM) == (4, 2, 4)
    assert (v.MIN_TEXT_CHARS, v.MAX_ARGUMENT_CHARS, v.MAX_REBUTTAL_CHARS) == (20, 360, 280)
    assert (v.MAX_POINT_CHARS, v.MAX_SIDE_CHARS, v.MAX_QUESTION_CHARS) == (300, 240, 200)
    assert (v.MAX_SHARED_POINTS, v.MAX_CONTESTED_POINTS, v.MAX_OPEN_QUESTIONS) == (3, 3, 3)


# ---------------------------------------------------------------------------
# One case per discard code
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("item", [
    arg(theme="tema_inventato"),
    arg(stance="favorevole"),
    arg(fact_ids="F9"),
    arg(fact_ids=["F9", 9]),
    arg(text=None),
    {"theme": "costi", "stance": "neutro", "fact_ids": ["F9"]},
    arg(text="Troppo corto {F9}."),  # 18 chars after normalization
    "non un oggetto",
])
def test_code_schema_non_valido(case_file, item) -> None:
    assert opening_code(case_file, item) == "schema_non_valido"


def test_schema_non_valido_contested_sides_not_two(case_file, admitted_args, admitted_rebs) -> None:
    point = {"text": "Il peso della posizione principale vale {F5} del portafoglio.", "fact_ids": ["F5"],
             "sides": [{"argument_ids": ["A-IND-2"], "summary": "Per l'indicizzatore il peso è eccessivo.",
                        "fact_ids": ["F5"]}]}
    res = v.verify_synthesis({"shared_points": [], "contested_points": [point], "open_questions": []},
                             case_file, admitted_args, admitted_rebs)
    assert [(d.path, d.code) for d in res.discarded] == [("contested_points[0]", "schema_non_valido")]


def test_code_riferimento_non_ammesso_rebuttal(case_file, admitted_args) -> None:
    raw = {"rebuttals": [
        {"target_argument_id": "A-IND-1", "stance": "concorda", "text": OK_TEXT, "fact_ids": ["F9"]},
        {"target_argument_id": "A-FAT-9", "stance": "concorda", "text": OK_TEXT, "fact_ids": ["F9"]},
        {"target_argument_id": "R-FAT-1", "stance": "concorda", "text": OK_TEXT, "fact_ids": ["F9"]},
        {"target_argument_id": "A-FAT-1", "stance": "concorda", "text": OK_TEXT, "fact_ids": ["F9"]},
    ]}
    res = v.verify_rebuttals("indicizzatore", raw, case_file, admitted_args)
    assert [d.code for d in res.discarded] == ["riferimento_non_ammesso"] * 3
    assert [d.path for d in res.discarded] == ["rebuttals[0]", "rebuttals[1]", "rebuttals[2]"]
    assert res.admitted[0]["id"] == "R-IND-1"
    assert res.admitted[0]["target_voice"] == "fattoriale"


def test_code_riferimento_non_ammesso_synthesis(case_file, admitted_args, admitted_rebs) -> None:
    raw = {
        "shared_points": [
            # unknown id
            {"text": "Le voci concordano sulla quota azionaria di {F1}.", "fact_ids": ["F1"],
             "argument_ids": ["A-FAT-3", "A-PRU-9"]},
            # only one voice
            {"text": "Le voci concordano sulla quota azionaria di {F1}.", "fact_ids": ["F1"],
             "argument_ids": ["A-FAT-3", "A-FAT-2"]},
        ],
        "contested_points": [
            # side without argument_ids
            {"text": "Quanto pesa la posizione principale, che vale {F5}.", "fact_ids": ["F5"],
             "sides": [{"argument_ids": [], "summary": "Per una voce il peso è eccessivo davvero.", "fact_ids": ["F5"]},
                       {"argument_ids": ["A-FAT-2"], "summary": "Per l'altra è una scelta consapevole.", "fact_ids": ["F5"]}]},
            # shared voice between sides
            {"text": "Quanto pesa la posizione principale, che vale {F5}.", "fact_ids": ["F5"],
             "sides": [{"argument_ids": ["A-IND-2"], "summary": "Per una voce il peso è eccessivo davvero.", "fact_ids": ["F5"]},
                       {"argument_ids": ["R-IND-1", "A-FAT-2"], "summary": "Per l'altra è una scelta consapevole.", "fact_ids": ["F5"]}]},
        ],
        "open_questions": [],
    }
    res = v.verify_synthesis(raw, case_file, admitted_args, admitted_rebs)
    assert [(d.path, d.code) for d in res.discarded] == [
        ("shared_points[0]", "riferimento_non_ammesso"),
        ("shared_points[1]", "riferimento_non_ammesso"),
        ("contested_points[0]", "riferimento_non_ammesso"),
        ("contested_points[1]", "riferimento_non_ammesso"),
    ]
    assert res.admitted_count == 0


def test_code_nessun_fatto(case_file) -> None:
    assert opening_code(case_file, arg(text="Il portafoglio ha costi contenuti e una struttura semplice.",
                                       fact_ids=[])) == "nessun_fatto"


def test_code_troppi_fatti(case_file) -> None:
    assert opening_code(case_file, arg(fact_ids=["F9", "F1", "F2", "F3", "F5"])) == "troppi_fatti"
    # duplicates collapse: 4 distinct facts are fine
    item = opening_admitted(case_file, arg(fact_ids=["F9", "F1", "F9", "F2", "F3", "F1"]))
    assert item["fact_ids"] == ["F9", "F1", "F2", "F3"]


def test_code_fatto_inesistente(case_file) -> None:
    assert opening_code(case_file, arg(fact_ids=["F99"])) == "fatto_inesistente"
    assert opening_code(case_file, arg(fact_ids=["F012"])) == "fatto_inesistente"
    # placeholder pointing to a missing fact
    assert opening_code(case_file, arg(text="Il TER medio è {F9} e il dato extra è {F88}.",
                                       fact_ids=["F9"])) == "fatto_inesistente"


def test_code_fatto_non_citabile(case_file) -> None:
    assert opening_code(case_file, arg(text="La regola personale sugli Stati Uniti è {F37}.",
                                       fact_ids=["F37"])) == "fatto_non_citabile"
    # placeholder-only use of a non-citable fact
    assert opening_code(case_file, arg(text="Il TER medio è {F9} e il recupero è {F24}.",
                                       fact_ids=["F9"])) == "fatto_non_citabile"


@pytest.mark.parametrize("text", [
    "Il TER medio ponderato è {F 9}, un livello basso.",
    "Il TER medio ponderato è {f9}, un livello basso.",
    "Il TER medio ponderato è {F09}, un livello basso.",
    "Il TER medio ponderato è {FATTO}, un livello basso.",
    "Il TER medio ponderato è {F9}} un livello basso.",
    "Il TER medio ponderato è {F9, un livello basso.",
])
def test_code_segnaposto_malformato(case_file, text) -> None:
    assert opening_code(case_file, arg(text=text)) == "segnaposto_malformato"


def test_code_segnaposto_non_citato(case_file) -> None:
    assert opening_code(case_file, arg(text="Il TER medio è {F9} e la quota azionaria {F1}.",
                                       fact_ids=["F9"])) == "segnaposto_non_citato"


def test_segnaposto_non_citato_open_question(case_file) -> None:
    raw = {"shared_points": [], "contested_points": [],
           "open_questions": [{"text": "Quanto conta per te una quota azionaria di {F1}?"}]}
    res = v.verify_synthesis(raw, case_file, [], [])
    assert [(d.path, d.code) for d in res.discarded] == [("open_questions[0]", "segnaposto_non_citato")]


def test_code_fatto_estraneo(case_file, admitted_args, admitted_rebs) -> None:
    raw = {
        "shared_points": [
            # F10 is not cited by A-FAT-3 (F1) nor R-PRU-1 (F1, F27)
            {"text": "Le voci concordano su un punteggio di salute pari a {F10}.", "fact_ids": ["F10"],
             "argument_ids": ["A-FAT-3", "R-PRU-1"]},
        ],
        "contested_points": [
            # side cites F11, nobody among the referenced items cites it
            {"text": "Quanto pesa la posizione principale, che vale {F5}.", "fact_ids": ["F5"],
             "sides": [{"argument_ids": ["A-IND-2"], "summary": "Per l'indicizzatore la volatilità è {F11}.", "fact_ids": ["F11"]},
                       {"argument_ids": ["A-FAT-2"], "summary": "Per il fattoriale è una scelta consapevole.", "fact_ids": ["F8"]}]},
        ],
        "open_questions": [],
    }
    res = v.verify_synthesis(raw, case_file, admitted_args, admitted_rebs)
    assert [(d.path, d.code) for d in res.discarded] == [
        ("shared_points[0]", "fatto_estraneo"), ("contested_points[0]", "fatto_estraneo")]


def test_code_testo_troppo_lungo(case_file) -> None:
    base = "Il TER medio ponderato è {F9}, un livello coerente con una gestione passiva"
    exact = base + "." + " a" * ((v.MAX_ARGUMENT_CHARS - len(base) - 1) // 2)
    exact = exact.ljust(v.MAX_ARGUMENT_CHARS, "a")[: v.MAX_ARGUMENT_CHARS]
    assert len(exact) == v.MAX_ARGUMENT_CHARS
    assert opening_code(case_file, arg(text=exact)) is None
    assert opening_code(case_file, arg(text=exact + "a")) == "testo_troppo_lungo"


def test_testo_troppo_lungo_limits_per_type(case_file, admitted_args, admitted_rebs) -> None:
    long_reb = "Il TER medio ponderato è {F9}, un livello basso " + "e " * 120
    res = v.verify_rebuttals("indicizzatore", {"rebuttals": [
        {"target_argument_id": "A-FAT-1", "stance": "precisa", "text": long_reb, "fact_ids": ["F9"]}]},
        case_file, admitted_args)
    assert [d.code for d in res.discarded] == ["testo_troppo_lungo"]
    long_q = "Che ruolo vuoi dare alla componente obbligazionaria " + "e " * 80 + "?"
    res = v.verify_synthesis({"shared_points": [], "contested_points": [],
                              "open_questions": [{"text": long_q}]}, case_file, [], [])
    assert [d.code for d in res.discarded] == ["testo_troppo_lungo"]
    side = "Per l'indicizzatore il peso è eccessivo " + "e " * 110
    point = {"text": "Quanto pesa la posizione principale, che vale {F5}.", "fact_ids": ["F5"],
             "sides": [{"argument_ids": ["A-IND-2"], "summary": side, "fact_ids": ["F6"]},
                       {"argument_ids": ["A-FAT-2"], "summary": "Per il fattoriale è una scelta consapevole.",
                        "fact_ids": ["F8"]}]}
    res = v.verify_synthesis({"shared_points": [], "contested_points": [point], "open_questions": []},
                             case_file, admitted_args, admitted_rebs)
    assert [d.code for d in res.discarded] == ["testo_troppo_lungo"]


@pytest.mark.parametrize("text", [
    "Il TER è {F9}, ma IWVL potrebbe rafforzare il tilt value.",          # unknown ticker
    "Il TER è {F9}, inferiore a quello di IE00B4L5Y983 in generale.",     # unknown ISIN
    "Il TER è {F9}: un livello MOLTO basso per il portafoglio.",        # emphasis caps
    "Il TER è {F9}, più basso di un fondo Amundi comparabile.",           # issuer not held
    "Il TER è {F9}, più basso di un fondo J.P. Morgan comparabile.",      # issuer with dots
])
def test_code_strumento_non_ammesso(case_file, text) -> None:
    assert opening_code(case_file, arg(text=text)) == "strumento_non_ammesso"


@pytest.mark.parametrize("text", [
    "Il TER è {F9} e VWCE.DE resta il fondo principale del portafoglio.",
    "Il TER è {F9} e SXRV pesa sulla parte tecnologica del portafoglio.",
    "Il TER è {F9} e IE00BK5BQT80 è il fondo principale del portafoglio.",
    "Il TER è {F9}: i fondi iShares e Vanguard sono già nel portafoglio.",
    "Il TER è {F9} per gli ETF UCITS e l'esposizione USA resta ampia.",
])
def test_instruments_in_case_file_are_admitted(case_file, text) -> None:
    assert opening_code(case_file, arg(text=text)) is None


@pytest.mark.parametrize("text", [
    "Gli Stati Uniti pesano circa il 57% sulla parte scomposta del portafoglio.",
    "Il TER è {F9} e le top 3 posizioni dominano il portafoglio.",
    "Il TER è {F9}, ma nel 2030 la situazione potrebbe cambiare molto.",
    "Il TER è {F9}, al 10° posto tra i portafogli simili osservati.",
    "Il TER è {F9}, cioè circa la metà di un fondo attivo tipico.",
    "Il TER è {F9}, mantenuto stabile per dieci anni consecutivi.",
    "Il TER è {F9}, in calo di venti per cento rispetto al passato.",
    "Il TER è {F9}, frutto di vent'anni di scelte coerenti nel tempo.",
    "Il TER è {F9}, meno di trentotto punti base su base annua.",
    "Il TER è {F9}, pochi punti per cento sul rendimento atteso.",
    "Il TER è {F9}, il doppio dello scorso esercizio contabile.",
    "Il TER è {F9}, un valore espresso in % sul patrimonio investito.",
    "Il TER è {F9}, contro un costo di gestione in € piuttosto alto.",
    "Il TER è {F9}, contro un costo pari a ½ di quello medio di mercato.",
    "Il TER è {F9}, contro un costo pari a ２ volte quello medio di mercato.",
    "Il TER è {F9}, con un costo del portafoglio elevato al quadrato².",
])
def test_code_cifra_libera(case_file, text) -> None:
    assert opening_code(case_file, arg(text=text, fact_ids=["F9", "F15"])) == "cifra_libera"


@pytest.mark.parametrize("text, fact_ids", [
    ("Nella crisi del 2008 l'impatto stimato sarebbe stato di {F21} sul portafoglio.", ["F21"]),
    ("Nel ribasso del 2000-2002 l'impatto stimato è {F23} per il portafoglio.", ["F23"]),
    ("Le prime tre posizioni valgono {F6}: due voci su tre lo leggono come concentrazione.", ["F6"]),
    ("Con una sola posizione da {F5} il primo fondo domina il secondo e il terzo.", ["F5"]),
    ("Il TER è {F9}: sei al riparo da costi alti con una scelta decennale.", ["F9"]),
    ("Il TER è {F9} e la liquidità non è considerata nel calcolo dei costi.", ["F9"]),
])
def test_free_figure_exceptions_admitted(case_file, text, fact_ids) -> None:
    assert opening_code(case_file, arg(text=text, fact_ids=fact_ids)) is None


def test_internal_ids_in_text_are_discarded(case_file) -> None:
    # F12 / A-IND-1 contain digits (§7.4) but also match the ticker regex (§7.5, check 11),
    # which comes first in the precedence order.
    for text in ("Il TER è {F9}, contro il valore F12 di un altro fattore del fascicolo.",
                 "Il TER è {F9}, come indicato nell'argomento A-IND-1 della seduta."):
        assert opening_code(case_file, arg(text=text)) == "strumento_non_ammesso"
    # lowercase id: no ticker match, the digit makes it a free figure
    assert opening_code(case_file, arg(text="Il TER è {F9}, come nell'argomento a-ind-1 della seduta.")) \
        == "cifra_libera"


def test_year_allowed_only_with_matching_label(case_file) -> None:
    text = "Nella crisi del 2008 l'impatto stimato sarebbe stato di {F27} sul portafoglio."
    assert opening_code(case_file, arg(text=text, fact_ids=["F27"])) == "cifra_libera"
    # the year label can come from a fact cited only in fact_ids (not as placeholder)
    assert opening_code(case_file, arg(text=text, fact_ids=["F27", "F21"])) is None


def test_instrument_identifier_with_digits_is_not_free_figure() -> None:
    cf = {"instruments": [{"symbol": "X25E.DE", "isin": "LU0290355717", "name": "Xtrackers Eurozone Gov Bond 25+"}],
          "facts": [{"id": "F1", "key": "metric.bond_weight_pct", "label": "Quota obbligazionaria",
                     "formatted": "17,4%", "citable": True}]}
    for text in ("La quota obbligazionaria è {F1}, quasi tutta in X25E.DE.",
                 "La quota obbligazionaria è {F1}, quasi tutta in X25E nel portafoglio.",
                 "La quota obbligazionaria è {F1}, quasi tutta in LU0290355717 ora."):
        res = v.verify_opening("prudente", {"arguments": [arg(text=text, fact_ids=["F1"])]}, cf)
        assert res.discarded == [], text
    res = v.verify_opening("prudente", {"arguments": [arg(
        text="La quota obbligazionaria è {F1}, quasi tutta in X26E nel portafoglio.", fact_ids=["F1"])]}, cf)
    assert [d.code for d in res.discarded] == ["strumento_non_ammesso"]


@pytest.mark.parametrize("text", [
    "Il TER è {F9}, ma conviene comprare più obbligazioni per bilanciare.",
    "Il TER è {F9}: vendere la posizione principale ridurrebbe il rischio.",
    "Il TER è {F9}; sarebbe utile ribilanciare verso la parte difensiva.",
    "Il TER è {F9} e si consiglia di mantenere la struttura attuale.",
    "Il TER è {F9}, un portafoglio adeguato a un profilo dinamico.",
    "Il TER è {F9}, dovresti sostituire il fondo più costoso presente.",
    "Il TER è {F9}, frutto di acquisti successivi nel corso del tempo.",
])
def test_code_indicazione_operativa(case_file, text) -> None:
    assert opening_code(case_file, arg(text=text)) == "indicazione_operativa"


@pytest.mark.parametrize("text", [
    "Il TER è {F9}: su questo punto l'indicizzatore ha ragione senza dubbio.",
    "Il TER è {F9}, e la lettura del prudente è quella vincente oggi.",
    "Il TER è {F9}: il verdetto è chiaro per chi guarda ai costi.",
])
def test_code_verdetto(case_file, text) -> None:
    assert opening_code(case_file, arg(text=text)) == "verdetto"


def test_code_troppi_argomenti_opening(case_file) -> None:
    raw = {"arguments": [arg() for _ in range(6)]}
    res = v.verify_opening("fattoriale", raw, case_file)
    assert [a["id"] for a in res.admitted] == ["A-FAT-1", "A-FAT-2", "A-FAT-3", "A-FAT-4"]
    assert [(d.path, d.code) for d in res.discarded] == [
        ("arguments[4]", "troppi_argomenti"), ("arguments[5]", "troppi_argomenti")]


def test_discarded_items_do_not_take_a_slot(case_file) -> None:
    raw = {"arguments": [arg(fact_ids=["F99"]), arg(), arg(), arg(), arg(text="Il TER è circa 0,2%, basso."), arg()]}
    res = v.verify_opening("prudente", raw, case_file)
    assert [a["id"] for a in res.admitted] == ["A-PRU-1", "A-PRU-2", "A-PRU-3", "A-PRU-4"]
    assert [(d.path, d.code) for d in res.discarded] == [
        ("arguments[0]", "fatto_inesistente"), ("arguments[4]", "cifra_libera")]


def test_code_troppi_argomenti_rebuttals(case_file, admitted_args) -> None:
    reb = {"target_argument_id": "A-FAT-1", "stance": "precisa", "text": OK_TEXT, "fact_ids": ["F9"]}
    res = v.verify_rebuttals("prudente", {"rebuttals": [reb, reb, reb]}, case_file, admitted_args)
    assert [r["id"] for r in res.admitted] == ["R-PRU-1", "R-PRU-2"]
    assert [(d.path, d.code) for d in res.discarded] == [("rebuttals[2]", "troppi_argomenti")]


def test_code_troppi_argomenti_synthesis(case_file, admitted_args, admitted_rebs) -> None:
    shared = {"text": "Le voci concordano sulla quota azionaria di {F1}.", "fact_ids": ["F1"],
              "argument_ids": ["A-FAT-3", "R-PRU-1"]}
    question = {"text": "Quanta oscillazione temporanea saresti disposto ad accettare?"}
    raw = {"shared_points": [shared] * 4, "contested_points": [], "open_questions": [question] * 5}
    res = v.verify_synthesis(raw, case_file, admitted_args, admitted_rebs)
    assert [p["id"] for p in res.synthesis["shared_points"]] == ["S1", "S2", "S3"]
    assert [q["id"] for q in res.synthesis["open_questions"]] == ["Q1", "Q2", "Q3"]
    assert [(d.path, d.code) for d in res.discarded] == [
        ("shared_points[3]", "troppi_argomenti"),
        ("open_questions[3]", "troppi_argomenti"), ("open_questions[4]", "troppi_argomenti")]
    assert res.admitted_count == 6
    assert res.by_code() == {"troppi_argomenti": 3}


def test_every_code_is_covered() -> None:
    # guard: the module-level cases above exercise each code at least once
    names = {n for n in globals() if n.startswith("test_code_")}
    for code in v.DISCARD_CODES:
        assert any(code in n for n in names), code


# ---------------------------------------------------------------------------
# Precedence and format edge cases
# ---------------------------------------------------------------------------

def test_precedence_first_code_wins(case_file) -> None:
    # non-citable fact (6) and free figure (12) and operative (13): 6 wins
    assert opening_code(case_file, arg(text="Il recupero è {F24}, quindi conviene vendere il 50%.",
                                       fact_ids=["F24"])) == "fatto_non_citabile"
    # ticker (11) before free figure (12): fixture case «vent'anni» + IWVL
    assert opening_code(case_file, arg(text="Mediana a vent'anni {F33}, e IWVL rafforzerebbe il tilt.",
                                       fact_ids=["F33"])) == "strumento_non_ammesso"
    # malformed placeholder (7) before placeholder not cited (8)
    assert opening_code(case_file, arg(text="Il TER è {F9} e la quota {F1} con {F 2} in totale.",
                                       fact_ids=["F9"])) == "segnaposto_malformato"
    # length (10) before free figure (12)
    assert opening_code(case_file, arg(text="Il TER è {F9} e 5 " + "a" * 400)) == "testo_troppo_lungo"


def test_contested_point_checks_run_code_by_code(case_file, admitted_args, admitted_rebs) -> None:
    # point text has a free figure (12), second side a non-citable fact (6): 6 wins
    point = {"text": "Quanto pesa la posizione principale, che vale {F5} e il 47%.", "fact_ids": ["F5"],
             "sides": [{"argument_ids": ["A-IND-2"], "summary": "Per l'indicizzatore il peso è eccessivo.", "fact_ids": ["F6"]},
                       {"argument_ids": ["A-FAT-2"], "summary": "Per il fattoriale la regola è {F37}.", "fact_ids": ["F37"]}]}
    res = v.verify_synthesis({"shared_points": [], "contested_points": [point], "open_questions": []},
                             case_file, admitted_args, admitted_rebs)
    assert [d.code for d in res.discarded] == ["fatto_non_citabile"]


def test_normalization_and_rendering(case_file) -> None:
    raw_text = "  Il TER​ medio\n\tponderato è   {F9},‮ un livello basso.  "
    item = opening_admitted(case_file, arg(text=raw_text))
    assert item["text_template"] == "Il TER medio ponderato è {F9}, un livello basso."
    assert item["text"] == "Il TER medio ponderato è 0,19%, un livello basso."
    assert v.normalize_text(raw_text) == item["text_template"]


def test_min_length_measured_after_normalization(case_file) -> None:
    text = "Il TER è {F9} basso."  # 20 code points
    assert len(text) == v.MIN_TEXT_CHARS
    assert opening_code(case_file, arg(text=text)) is None
    assert opening_code(case_file, arg(text="  Il TER è {F9} bass  \n\n ")) == "schema_non_valido"


def test_render_template(case_file) -> None:
    assert v.render_template("{F21} in {F22}; {F10}; {F24}; {F999}", case_file) == \
        "-38,2% in 49 mesi; 71/100; N/D; {F999}"


def test_fact_in_fact_ids_without_placeholder_is_admitted(case_file) -> None:
    item = opening_admitted(case_file, arg(text="Il costo complessivo del portafoglio è contenuto.",
                                           fact_ids=["F9", "F1"]))
    assert item["fact_ids"] == ["F9", "F1"]
    assert item["text"] == item["text_template"]


def test_all_arguments_discarded(case_file) -> None:
    raw = {"arguments": [
        arg(text="Il TER è basso, circa 0,2% annuo per tutto il portafoglio."),
        arg(fact_ids=[]),
        arg(text="Il TER è {F9}: conviene comprare un ETF più economico."),
        arg(fact_ids=["F24"]),
    ]}
    res = v.verify_opening("indicizzatore", raw, case_file)
    assert res.admitted == []
    assert [d.code for d in res.discarded] == [
        "cifra_libera", "nessun_fatto", "indicazione_operativa", "fatto_non_citabile"]
    assert res.by_code() == {"cifra_libera": 1, "fatto_non_citabile": 1,
                             "indicazione_operativa": 1, "nessun_fatto": 1}
    assert list(res.by_code()) == sorted(res.by_code())


def test_discard_carries_no_text(case_file) -> None:
    res = v.verify_opening("indicizzatore", {"arguments": [arg(text="Testo segreto con 42 cifre e altro.")]}, case_file)
    assert res.discarded == [v.Discard("arguments[0]", "cifra_libera")]
    assert set(vars(res.discarded[0])) == {"path", "code"}


def test_missing_list_yields_empty_result(case_file) -> None:
    assert v.verify_opening("prudente", {}, case_file).admitted == []
    assert v.verify_rebuttals("prudente", {"rebuttals": None}, case_file, []).discarded == []
    syn = v.verify_synthesis({}, case_file, [], [])
    assert syn.synthesis == {"shared_points": [], "contested_points": [], "open_questions": []}
    assert syn.admitted_count == 0


def test_unknown_voice_raises(case_file) -> None:
    with pytest.raises(ValueError):
        v.verify_opening("ottimista", {"arguments": []}, case_file)
