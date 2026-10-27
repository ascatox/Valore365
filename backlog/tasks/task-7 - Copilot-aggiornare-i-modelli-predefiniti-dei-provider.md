---
id: TASK-7
title: 'Copilot: aggiornare i modelli predefiniti dei provider'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - copilot
  - backend
milestone: m-0
dependencies: []
priority: medium
type: chore
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
I modelli usati quando né l'utente né il server ne indicano uno (`_DEFAULT_MODELS` in `src/backend/app/copilot/config.py`) sono di generazioni precedenti: `claude-sonnet-4-20250514`, `gpt-4o-mini`, `gemini-2.0-flash`. Chi non sceglie un modello riceve risposte meno accurate di quelle disponibili oggi, a volte a un costo più alto del necessario. Gli identificativi correnti vanno verificati sulla documentazione dei provider al momento del lavoro; per Anthropic la famiglia attuale è Claude 5 (es. `claude-sonnet-5-5`, `claude-haiku-5-5`).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Ogni provider ha come predefinito un modello attualmente disponibile, verificato sulla documentazione ufficiale
- [ ] #2 Le opzioni di modello proposte nella pagina Impostazioni sono coerenti con i nuovi predefiniti
- [ ] #3 Le scelte di modello già salvate dagli utenti non cambiano
- [ ] #4 `.env.example` e i test che citano i vecchi identificativi sono aggiornati
<!-- AC:END -->
