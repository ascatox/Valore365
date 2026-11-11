---
id: TASK-73
title: 'Auditor: motore, contesto memoizzato e CLI'
status: Done
assignee: []
created_date: '2026-11-10T18:00:00Z'
labels:
  - auditor
  - backend
milestone: m-2
dependencies:
  - TASK-72
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le regole dell'Auditor hanno bisogno di un motore comune: un registro, un contesto che chiama i tool del server MCP una volta sola per esecuzione, un esecutore che isola gli errori di una regola dalle altre e una CLI che produce un report leggibile in CI e in locale.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Esistono registro, contesto, esecutore e modello del risultato con le firme di `docs/auditor/architecture.md`; una regola si registra con un decoratore o una dichiarazione e viene scoperta senza modificare il motore
- [x] #2 Il contesto chiama i tool tramite `run_tool_sync` con le stesse dipendenze del server MCP e memoizza ogni coppia (tool, argomenti) per l'esecuzione; un tool che solleva produce un esito `error` sulla regola, non interrompe l'esecuzione
- [x] #3 Una regola che solleva un'eccezione dà `error` con il nome dell'eccezione; una regola che supera il proprio timeout dà `error` con codice dedicato
- [x] #4 Il report contiene esiti per regola e per scope, conteggi per esito e severità, durata, versione dell'app; viene prodotto in JSON (schema del contratto) e in Markdown leggibile
- [x] #5 La CLI `python -m app.services.auditor` accetta utente, portafogli, gruppi o id di regole, formato e soglia di severità; esce con codice diverso da zero se c'è almeno un `fail` o `error` alla soglia indicata
- [x] #6 Test unitari con regole e tool finti coprono registrazione, memoizzazione, isolamento degli errori, timeout, filtri, report e codici di uscita
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/services/auditor/__init__.py`, `registry.py`, `context.py`, `runner.py`, `report.py`, `__main__.py`, `tests/unit/test_auditor_engine.py`. I file delle regole (`rules/`) sono dei task TASK-74…77: crea solo `rules/__init__.py` con l'importazione dei moduli dei gruppi, tollerante se un modulo non esiste ancora.
Parallelizzabile con TASK-74…78.
<!-- SECTION:NOTES:END -->
