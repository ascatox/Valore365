---
id: TASK-53
title: >-
  Prezzi: chiusure giornaliere per gli asset in portafoglio e segnalazione delle
  quotazioni ferme
status: In Progress
assignee: []
created_date: '2026-11-03T13:50:00Z'
labels:
  - backend
  - prezzi
milestone: m-1
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Retest MCP 2026-11-03 punto 5 e query Q10. Il job in background salva solo i price_ticks; le barre giornaliere (price_bars_1d, la price_date mostrata dai tool) vengono scritte solo da backfill manuali, dalla creazione di transazioni o dall'apertura della pagina dell'asset; il job delle 06:30 copre solo i benchmark. XAD1.DE (id 120, attivo, provider_symbol XAD1.DE): ultima barra 2026-10-30 e ultimo tick 2026-11-02 20:38, senza errori nei log, mentre gli altri .DE sono aggiornati alle 13:16 del 3/11. Ipotesi: Yahoo restituisce sempre lo stesso timestamp di mercato (ts = timestamp del provider), quindi nessun tick nuovo e nessun errore.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Job giornaliero (dopo la chiusura dei mercati) che salva la barra giornaliera per tutti gli asset attivi in portafoglio, riusando historical_service, con concorrenza e limiti esistenti
- [ ] #2 Quotazione ferma rilevata: se il timestamp del provider è indietro rispetto al calendario di borsa di più di N sedute, il prezzo è marcato stale con motivo, ed esposto in get_positions e get_day_movers
- [ ] #3 Log esplicito quando il provider restituisce lo stesso timestamp per un asset per più refresh consecutivi
- [ ] #4 Test con calendario di borsa, fine settimana e asset illiquido
<!-- AC:END -->
