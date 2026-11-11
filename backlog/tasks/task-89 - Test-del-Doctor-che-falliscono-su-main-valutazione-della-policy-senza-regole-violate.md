---
id: TASK-89
title: 'Test del Doctor che falliscono su main: valutazione della policy senza regole violate'
status: To Do
assignee: []
created_date: '2026-11-11T20:00:00Z'
labels:
  - backend
  - test
  - doctor
milestone: m-1
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Quattro test unitari falliscono su `main` da prima del lavoro sul Tribunale e sull'Auditor (almeno dal 2026-11-10), e ogni PR li riporta come «già rotti»:

- `tests/unit/test_copilot_doctor_tools.py::test_read_doctor_violations_lists_fail_and_flags_data_quality`
- `tests/unit/test_copilot_doctor_tools.py::test_preview_policy_hides_token_from_llm_and_emits_ui_event`
- `tests/unit/test_copilot_doctor_tools.py::test_llm_failure_surfaces_error_and_doctor_rest_still_works`
- `tests/unit/test_doctor_scenario_routes.py::test_preview_golden_over_rest`

Sintomo comune: la valutazione della policy del Doctor restituisce `summary.failed == 0` dove il test si aspetta una regola violata (`assert 0 == 1`). Può essere un difetto reale della valutazione (una regola che dovrebbe fallire risulta rispettata o non verificabile) oppure un test che dipende da qualcosa che è cambiato (data corrente, freschezza dei dati, classificazione, arrotondamenti). Va stabilito quale, perché un test rosso fisso nasconde i fallimenti nuovi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Causa individuata e documentata nelle note del task (con il commit che l'ha introdotta, se rintracciabile)
- [ ] #2 Se è un difetto del codice: corretto, con un test che lo dimostra; se è un difetto dei test: test corretti senza indebolire ciò che verificano
- [ ] #3 I quattro test passano e la suite unitaria è interamente verde
- [ ] #4 Se il difetto riguarda numeri visibili all'utente, aggiunta o aggiornata una regola dell'Auditor che lo intercetta
<!-- AC:END -->
