---
id: TASK-9
title: 'Copilot: suite di valutazione delle risposte'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - copilot
  - backend
  - ci
milestone: m-0
dependencies:
  - TASK-8
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il Copilot usa 18 tool, prompt diversi per pagina e 5 provider. Ogni modifica a prompt, tool o modello può peggiorare le risposte senza che nessun test se ne accorga: i test esistenti coprono streaming e contesto di pagina, non la qualità delle risposte. Serve un modo ripetibile per misurare se il modello sceglie i tool giusti e riporta numeri corretti, da usare prima di cambiare prompt o modello predefinito.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Esistono almeno 3 portafogli di esempio (es. un solo ETF globale, ETF sovrapposti, portafoglio concentrato con molta liquidità) e almeno 30 domande in italiano, ciascuna con i tool attesi
- [ ] #2 Uno script esegue le domande contro un provider reale e produce un report con: tool scelti corretti, numeri non verificati (con il controllo dei numeri), presenza del disclaimer, risposta in italiano
- [ ] #3 Lo script funziona senza database reale, con i soli dati di esempio
- [ ] #4 Un workflow CI esegue la suite sulle PR che modificano `src/backend/app/prompts/`, `src/backend/app/copilot/` o `src/backend/app/copilot_tools.py`, solo se il secret con la chiave API è configurato; altrimenti salta senza fallire
- [ ] #5 La documentazione del backend spiega come eseguire la suite in locale
<!-- AC:END -->
