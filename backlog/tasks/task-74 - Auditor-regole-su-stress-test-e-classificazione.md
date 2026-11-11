---
id: TASK-74
title: 'Auditor: regole su stress test e classificazione'
status: Done
assignee: []
created_date: '2026-11-10T18:00:00Z'
labels:
  - auditor
  - backend
  - doctor
milestone: m-2
dependencies:
  - TASK-72
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Ogni regola segue l'interfaccia di `docs/auditor/architecture.md`: id stabile, titolo in italiano, severità (P0/P1/P2), finding di origine, ambito (portafoglio, vista aggregata, strumento, globale), funzione che riceve il contesto e restituisce esito (`pass`, `fail`, `skip` con motivo) ed evidenza. Le regole leggono i dati solo tramite il contesto, che chiama i tool con `run_tool_sync` del server MCP: così verificano esattamente i numeri che vedono Copilot, Tribunale e Claude.

Per ogni regola un test unitario con un contesto finto dimostra due cose: la regola passa su dati corretti, e fallisce quando si reintroduce il difetto originale (riproducendo l'output sbagliato del finding, o con un monkeypatch del codice corretto). Una regola che non fallisce sul difetto che dichiara di intercettare non è accettata.

Gruppo A, dal catalogo di `docs/auditor/rules.md`: stress test e classificazione degli strumenti. Coprono V365-001 (stress storici identici per ogni portafoglio), V365-002 (bond, oro e commodity con lo shock azionario), V365-012 (ETC oro classificato come azione) e V-BOND-QUOTETYPE.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Sono implementate tutte le regole del gruppo A del catalogo, con id, severità e tolleranze del contratto
- [x] #2 Tra le regole: due portafogli con composizione diversa non hanno impatti storici identici su tutti gli scenari; nessuna posizione classificata obbligazionaria, oro o commodity riceve lo shock azionario negli scenari a shock; le contribuzioni per classe sommano all'impatto entro la tolleranza; un ETC su metalli preziosi non è classificato come azione
- [x] #3 Le regole vanno in `skip` con motivo quando i dati non bastano (portafoglio vuoto, scenario `not_available`), mai in `pass`
- [x] #4 Ogni regola ha il test che reintroduce il difetto originale e la vede fallire
- [x] #5 Le evidenze riportano tool, argomenti, valore osservato e valore atteso
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/services/auditor/rules/stress_classification.py`, `tests/unit/test_auditor_rules_stress.py`.
Riferimenti: `services/portfolio_doctor/_stress.py`, `constants/stress_scenarios.py`, `services/asset_classification.py`, `docs/audit-mcp-2026-11/methodology.md` §1 e §10.
Parallelizzabile con TASK-73, 75, 76, 77, 78. Usa un contesto finto con l'interfaccia del contratto, non il motore di TASK-73.
<!-- SECTION:NOTES:END -->
