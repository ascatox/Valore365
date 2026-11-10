---
id: TASK-65
title: 'Tribunale: orchestratore della seduta ed endpoint SSE'
status: To Do
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - doctor
  - tribunale
  - backend
  - api
milestone: m-0
dependencies:
  - TASK-61
  - TASK-62
  - TASK-63
  - TASK-64
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Con fascicolo, chiamata strutturata, voci e verificatore pronti, serve il pezzo che li mette in sequenza e li espone all'app: costruisce il fascicolo, interroga le tre voci in parallelo per l'apertura, poi per la replica, verifica ogni risposta, chiede la sintesi e invia tutto al frontend man mano, in streaming.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 L'endpoint di avvio seduta risponde in SSE con gli eventi, l'ordine e gli schemi di `docs/tribunale/api-contracts.md`, per portafoglio singolo e vista aggregata
- [ ] #2 Le tre voci di una stessa fase sono interrogate in parallelo e ogni argomento ammesso viene inviato appena verificato, senza attendere le altre voci
- [ ] #3 Se una voce fallisce o tutti i suoi argomenti sono scartati, la seduta prosegue con le altre e l'utente viene informato; con meno di due voci valide la seduta termina con un errore chiaro
- [ ] #4 La seduta rispetta un timeout complessivo e invia keepalive durante le attese, come il Copilot
- [ ] #5 Una variabile `DOCTOR_TRIBUNAL_ENABLED` (default `true`) spegne la funzione: gli endpoint rispondono 404 `feature_disabled` e `GET /api/doctor/features` lo espone
- [ ] #6 L'endpoint di stato dice se il Tribunale è utilizzabile con la configurazione Copilot dell'utente (chiave propria o del server, provider con risposta strutturata) e, se no, perché
- [ ] #7 Fascicolo e argomenti non vengono scritti nei log; i log riportano solo conteggi, durate e codici di scarto
- [ ] #8 Test con LLM finto coprono seduta completa, voce che fallisce, tutto scartato, timeout, feature spenta e scope di un altro utente
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/services/tribunal/orchestrator.py`, `src/backend/app/api/routes_tribunal.py`, la registrazione in `app/main.py`, il flag in `app/config.py` e `.env.example`, `tests/unit/test_tribunal_orchestrator.py`, `tests/unit/test_tribunal_routes.py`.
Riferimenti: `copilot/streaming.py` (`_run_with_heartbeat`, timeout, `_friendly_error`), `api/routes_copilot.py` (risoluzione della configurazione, `memoize_positions`), `api/routes_doctor.py` (feature flag e scope).
È il punto di integrazione del backend: un solo agente, dopo che TASK-61…64 sono chiusi.
<!-- SECTION:NOTES:END -->
