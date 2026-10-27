---
id: TASK-8
title: 'Copilot: verificare che i numeri citati nelle risposte esistano nei dati'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - copilot
  - backend
milestone: m-0
dependencies: []
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il prompt agentico (`src/backend/app/prompts/copilot_system_agentic.txt`) chiede al modello di non inventare numeri, ma nessun codice lo verifica: un importo o una percentuale inventati arrivano all'utente come se fossero calcolati dal Doctor, e contraddicono il principio del prodotto (il Doctor calcola, l'AI spiega). Serve un controllo riutilizzabile che confronti i numeri del testo generato con quelli presenti nello snapshot e negli output dei tool. Lo stesso controllo servirà alla suite di valutazione e a ogni altro testo generato dall'AI (commento al rendiconto, riepilogo settimanale).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Dato un testo e i dati di origine, il controllo restituisce l'elenco dei numeri non riconducibili ai dati
- [ ] #2 Gestisce il formato italiano (1.234,56), percentuali, importi in euro e arrotondamenti al numero di decimali mostrato
- [ ] #3 Non segnala date, anni, numeri presenti nella domanda dell'utente o nel disclaimer
- [ ] #4 A fine risposta il Copilot registra nei log i numeri non verificati e invia al frontend un evento SSE dedicato, senza interrompere lo streaming
- [ ] #5 Test unitari coprono casi verificati, non verificati e formati diversi
<!-- AC:END -->
