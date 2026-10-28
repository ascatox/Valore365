---
id: TASK-19
title: 'Dati ETF: estrazione dei campi mancanti da KID e factsheet'
status: To Do
assignee: []
created_date: '2026-10-27T20:27:00Z'
labels:
  - ai
  - etf
  - backend
  - data
milestone: m-0
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
X-Ray, Doctor e Copilot dipendono dai metadati ETF in `etf_enrichment`, che oggi arrivano da justETF e FMP (`src/backend/app/justetf_client.py`). Per diversi ETF mancano campi come metodo di replica, politica di distribuzione, domicilio e copertura valutaria, e le analisi risultano incomplete. Questi dati sono nei documenti ufficiali (KID, factsheet), da cui il modello può estrarli in forma strutturata.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un job individua gli ETF con campi mancanti e li completa leggendo KID o factsheet
- [ ] #2 I valori estratti sono validati su valori ammessi (es. replica fisica o sintetica) e salvati con fonte e data
- [ ] #3 I valori estratti non sovrascrivono mai valori già forniti da fonti strutturate
- [ ] #4 Il job rispetta limiti di frequenza e non ripete l'estrazione per documenti già elaborati
- [ ] #5 X-Ray e Copilot usano i campi completati
- [ ] #6 Test con documento di esempio e provider simulato
<!-- AC:END -->
