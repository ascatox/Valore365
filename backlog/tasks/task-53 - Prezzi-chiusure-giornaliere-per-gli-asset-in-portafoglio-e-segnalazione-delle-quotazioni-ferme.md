---
id: TASK-53
title: >-
  Prezzi: chiusure giornaliere per gli asset in portafoglio e segnalazione delle
  quotazioni ferme
status: Done
assignee: []
created_date: '2026-11-03T13:50:00Z'
updated_date: '2026-11-03T14:05:00Z'
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
- [x] #1 Job giornaliero (dopo la chiusura dei mercati) che salva la barra giornaliera per tutti gli asset attivi in portafoglio, riusando historical_service, con concorrenza e limiti esistenti
- [x] #2 Quotazione ferma rilevata: se il timestamp del provider è indietro rispetto al calendario di borsa di più di N sedute, il prezzo è marcato stale con motivo, ed esposto in get_positions e get_day_movers
- [x] #3 Log esplicito quando il provider restituisce lo stesso timestamp per un asset per più refresh consecutivi
- [x] #4 Test con calendario di borsa, fine settimana e asset illiquido
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Job giornaliero delle chiusure (lun-ven 22:30 UTC, ultimi 10 giorni, tutti gli asset attivi in portafoglio). Quotazione ferma calcolata sulle sedute della borsa dell'asset (fine settimana e festività principali esclusi), con stale_reason e last_price_at in posizioni, summary e day movers; funziona anche senza scheduler. Log price_unchanged_ts e unchanged_ts_symbols nel refresh. Causa probabile di XAD1: get_daily_bars scartava senza log le sedute con chiusura presente ma open/high/low/adjclose null (tipico dei listing Xetra poco scambiati); ora sono conservate (valori mancanti presi dalla chiusura) e registrate come daily_bars_partial_rows; log per asset daily_bars_no_new_bar e daily_bars_rejected. Dai log di produzione lo scheduler a intervalli non gira (refresh solo manuali): verificare PRICE_SCHEDULER_ENABLED e se l'istanza Render va in sospensione. Test: test_task53_daily_bars_and_stale_prices.py (25); 986 passed.
<!-- SECTION:FINAL_SUMMARY:END -->
