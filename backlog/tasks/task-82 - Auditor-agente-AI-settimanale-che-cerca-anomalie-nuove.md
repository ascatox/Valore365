---
id: TASK-82
title: 'Auditor: agente AI settimanale che cerca anomalie nuove'
status: Done
assignee: []
created_date: '2026-11-10T18:00:00Z'
labels:
  - auditor
  - ai
  - ci
milestone: m-2
dependencies:
  - TASK-79
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le regole intercettano solo i difetti che qualcuno ha già immaginato. L'audit di novembre li ha trovati facendo domande come un utente scettico e incrociando i tool. Questo lavoro va reso periodico: una sessione AI settimanale, con il playbook di `docs/auditor/agent-playbook.md`, esplora i tool sui portafogli di prova, cerca valori implausibili e incoerenze, e propone nuove regole e nuovi task. Non corregge mai il codice.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Uno script consente all'agente di chiamare qualunque tool esposto dal server MCP sui portafogli di prova in locale, senza login Clerk, stampando il risultato JSON
- [x] #2 Il playbook è eseguibile da una sessione Claude programmata: avvia lo stack locale con il seed dell'Auditor, esegue l'Auditor, poi esplora i tool secondo la metodologia
- [x] #3 Per ogni sospetto l'agente produce un'evidenza riproducibile (tool, argomenti, output, motivo), verifica che non sia già coperto da una regola o da un task nel backlog, e solo allora lo propone
- [x] #4 L'esito della sessione è una PR in bozza con un report in `docs/auditor/reports/<data>.md`, i task proposti in `backlog/tasks/` e, per ogni sospetto confermato, la bozza di una nuova regola per il catalogo; nessuna modifica al codice applicativo
- [x] #5 Una prova a secco documentata mostra una sessione completa sul seed, con il report prodotto
- [x] #6 La documentazione spiega come attivare la sessione settimanale, quanto costa indicativamente e come disattivarla
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `scripts/auditor/mcp_call.py`, `scripts/auditor/agent_stack.sh`, `docs/auditor/agent-playbook.md` (aggiornamenti), `docs/auditor/reports/`.
L'attività programmata viene creata dalla sessione Claude che coordina il lavoro, dopo che lo script e la prova a secco sono pronti, e solo con la conferma del proprietario del progetto.
Riferimenti: `scripts/e2e/doctor2_stack.sh`, `app/mcp_server/tools.py`, `docs/audit-mcp-2026-11/methodology.md`.
<!-- SECTION:NOTES:END -->
