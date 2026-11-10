---
id: TASK-62
title: 'Copilot: chiamata LLM con risposta strutturata per tutti i provider'
status: Done
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - copilot
  - tribunale
  - backend
milestone: m-0
dependencies:
  - TASK-60
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Oggi il Copilot sa fare due cose con un modello: testo in streaming e tool calling dentro il loop agentico. Il Tribunale ha bisogno di una terza: chiedere una risposta che rispetti uno schema JSON e riceverla già validata, con lo stesso codice per OpenAI, Anthropic, Gemini e OpenRouter. È un mattone riusabile anche fuori dal Tribunale (riepilogo settimanale, commento al rendiconto).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Esiste una funzione che, dati configurazione Copilot, prompt di sistema, messaggi e uno schema JSON, restituisce un dizionario conforme allo schema oppure solleva un errore tipizzato
- [x] #2 Funziona con OpenAI, Anthropic, Gemini e OpenRouter usando il meccanismo di tool forzato o output strutturato di ciascun provider
- [x] #3 Per il provider locale senza tool calling la funzione dichiara che la capacità non è disponibile, senza tentare la chiamata
- [x] #4 Una risposta non conforme allo schema provoca un solo nuovo tentativo, poi l'errore tipizzato; timeout ed errori del provider sono distinguibili da quelli di schema
- [x] #5 Il comportamento del Copilot esistente (chat, loop agentico, streaming) non cambia: i test attuali passano senza modifiche
- [x] #6 Test unitari con client finti coprono, per ogni provider, risposta valida, risposta non conforme, timeout ed errore del provider
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: nuovo `src/backend/app/copilot/structured.py` e `tests/unit/test_copilot_structured.py`. Evitare di modificare `copilot/providers.py`; se serve estrarre un helper condiviso, farlo senza cambiare le firme esistenti.
Riferimenti: `_call_openai_with_tools`, `_call_anthropic_with_tools`, `_call_gemini_with_tools` in `copilot/providers.py`; `CopilotConfig` in `copilot/config.py`.
Parallelizzabile con TASK-61, 63, 64, 67.
<!-- SECTION:NOTES:END -->
