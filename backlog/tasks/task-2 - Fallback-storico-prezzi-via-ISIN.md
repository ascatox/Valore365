---
id: TASK-2
title: Fallback storico prezzi via ISIN quando il simbolo Yahoo non ha storico
status: Done
assignee: []
created_date: '2026-10-06 15:50'
labels:
  - backend
  - pricing
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il ticker 0GGH.L (iShares Global Aggregate Bond EUR Hedged, ISIN IE00BDBRDM35) risulta sempre senza storico: Yahoo restituisce la quotazione live ma nessuna (o una sola) barra giornaliera. Il backfill salvava zero/una barra senza tentare altre quotazioni dello stesso ISIN (AGGH.AS, AGGH.MI, EUNA.DE con storico completo).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il backfill rileva storico insufficiente (< 50% dei giorni lavorativi) o errore no_data
- [x] #2 Prova i candidati OpenFIGI dello stesso ISIN con prezzo entro il 5% dell'ultima chiusura/quotazione nota
- [x] #3 Aggiorna asset_provider_symbols con il simbolo alternativo trovato
- [x] #4 Test unitari per switch, scarto per prezzo, errore provider, assenza ISIN
<!-- AC:END -->
