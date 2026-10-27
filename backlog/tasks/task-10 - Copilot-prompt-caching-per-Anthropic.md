---
id: TASK-10
title: 'Copilot: prompt caching per Anthropic'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - copilot
  - backend
  - performance
milestone: m-0
dependencies: []
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Ogni chiamata del Copilot reinvia per intero il prompt di sistema e le definizioni dei 18 tool, fino a 5 round per domanda. Con Anthropic questa parte può essere messa in cache, riducendo costo e latenza delle chiamate successive; oggi `cache_control` non è usato da nessuna parte. Il costo pesa soprattutto sulla chiave server, che paga per gli utenti senza chiave propria.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Le chiamate Anthropic (tool calling e streaming) marcano come memorizzabili le definizioni dei tool e la parte stabile del prompt di sistema
- [ ] #2 I token letti dalla cache e scritti in cache vengono registrati nei log per ogni chiamata
- [ ] #3 In una conversazione con più round, le chiamate successive alla prima leggono dalla cache (verificato con un test sul payload della richiesta)
- [ ] #4 Il comportamento con gli altri provider non cambia
<!-- AC:END -->
