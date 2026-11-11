---
id: TASK-72
title: 'Auditor: contratto, catalogo delle regole e architettura'
status: Done
assignee: []
created_date: '2026-11-10T18:00:00Z'
labels:
  - auditor
  - backend
  - docs
milestone: m-2
dependencies: []
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
L'audit MCP di novembre 2026 ha trovato 24 anomalie nei numeri dei tool (`docs/audit-mcp-2026-11/audit-findings.md`), tre gravi: stress test storici identici per ogni portafoglio (V365-001), obbligazioni e oro con lo shock azionario (V365-002), ribilanciamento che contava due volte la liquidità (V365-003). Nessun test le aveva viste: i test controllano che il codice faccia ciò che lo sviluppatore pensava, non che i numeri abbiano senso finanziario e siano coerenti tra i tool. Ora il Tribunale fa discutere tre voci AI citando proprio quei numeri.

L'Auditor rende l'audit continuo, su due livelli: regole deterministiche (invarianti) eseguite in CI sui portafogli di prova e ogni notte in produzione, e un agente AI settimanale che cerca anomalie nuove e le trasforma in task. Questo task scrive il contratto comune che i task TASK-73…82 implementano in parallelo, come `docs/tribunale/` per il Tribunale.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Esiste `docs/auditor/architecture.md` con: moduli in `src/backend/app/services/auditor/`, firme pubbliche di registro, regola, contesto, esecutore, risultato e report; la tabella task → file di proprietà per TASK-73…82; le tre modalità di esecuzione (CI su fixture, notturna in produzione, agente settimanale) con cosa leggono e dove scrivono
- [x] #2 Il documento definisce lo schema del risultato di una regola e del report di un'esecuzione (JSON Schema ed esempio), con codici di esito `pass` / `fail` / `skip` / `error`, severità P0/P1/P2 e codice di uscita della CLI
- [x] #3 Il contesto chiama i tool tramite `run_tool_sync` di `app/mcp_server/tools.py` con memoizzazione per esecuzione; il documento elenca quali tool usa ciascun gruppo di regole e come si ottengono gli scope (singolo, aggregato, strumento)
- [x] #4 Esiste `docs/auditor/rules.md`: catalogo di tutte le regole previste (id, titolo, severità, finding di origine, tool letti, condizione esatta, tolleranze numeriche, quando la regola va in `skip`) per i quattro gruppi di TASK-74…77; ogni finding P0 e P1 del rapporto di novembre è coperto da almeno una regola oppure è indicato perché non è verificabile con un'invariante
- [x] #5 Il documento fissa la privacy: cosa contiene un'evidenza in CI (tutto, sono dati di prova), cosa si salva della corsa notturna in produzione (solo id regola, esito, portafoglio, severità, nessun importo né nome di strumento) e cosa vede l'utente
- [x] #6 Esiste `docs/auditor/agent-playbook.md` con il mandato dell'agente settimanale: metodologia (dalla metodologia dell'audit di novembre), formato di un sospetto, criteri per promuoverlo a finding, deduplica con backlog e regole, divieto di correggere codice
- [x] #7 Nessun codice applicativo viene modificato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Modelli: `docs/tribunale/` (contratto, architettura, tabella di proprietà), `docs/audit-mcp-2026-11/` (metodologia, finding, decisioni), `scripts/audit/twr_mwr_offline_auditor.py` (ricalcolo indipendente di TWR/XIRR, da riusare in TASK-77).
Riferimenti: `app/mcp_server/tools.py` (`run_tool_sync`, `EXPOSED_TOOL_NAMES`, tool aggregati in `aggregate_tools.py`), `app/copilot_tools.py` (definizioni dei 18 tool), `app/api/routes_internal.py` (endpoint interno con token: modello per la corsa notturna).
Va fatto per primo, da un solo agente.
<!-- SECTION:NOTES:END -->
