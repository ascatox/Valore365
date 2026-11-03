---
id: TASK-54
title: >-
  Sincronizzazione dei dati di mercato affidabile: trigger esterno (GitHub
  Actions) e recupero all'avvio
status: Done
assignee: []
created_date: '2026-11-03T17:20:00Z'
updated_date: '2026-11-03T17:40:00Z'
labels:
  - backend
  - prezzi
  - infra
milestone: m-1
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Specifica del proprietario (2026-11-03). Dai log di produzione lo scheduler interno non gira in modo affidabile (probabile sospensione dell'istanza Render). Requisiti: (1) lo scheduler interno non è l'unico responsabile della sincronizzazione; (2) un aggiornamento mancato si recupera al successivo avvio o trigger esterno; (3) due trigger simultanei non eseguono due sincronizzazioni concorrenti; (4) lo stato last_successful_price_sync è persistente; (5) un aggiornamento parziale o fallito non è registrato come completato; (6) l'endpoint amministrativo è autenticato e protetto; (7) le chiamate MCP restituiscono la freschezza dei dati oltre ai valori; (8) nessuna ipotesi che ogni giorno sia di negoziazione per tutti i mercati. Scelta: GitHub Actions (cron) + recupero automatico all'avvio. Il meccanismo deve poter includere in futuro cambi, dati ETF e altre informazioni di mercato.

Decisioni di progetto: tabelle additive market_data_sync_runs (esecuzioni) e market_data_asset_sync (stato per asset); lock con pg_try_advisory_lock; endpoint POST /api/internal/market-data/sync (202 + run_id) e GET .../sync/status protetti da token Bearer MARKET_DATA_SYNC_TOKEN (confronto a tempo costante, endpoint disattivato se il token manca); una run è success solo se ogni asset è aggiornato all'ultima seduta conclusa della sua borsa, altrimenti partial o failed; last_successful_price_sync avanza solo su success, mentre lo stato per asset avanza comunque; passi: quotazioni, barre giornaliere (dall'ultima sincronizzazione riuscita, con un limite), cambi delle valute in uso.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Migrazione additiva con tabelle di stato; nessuna modifica alle tabelle esistenti
- [x] #2 Due trigger simultanei: il secondo riceve 'già in corso' e non avvia una seconda sincronizzazione (test)
- [x] #3 Run parziale o fallita non aggiorna last_successful_price_sync (test)
- [x] #4 Recupero all'avvio in background se l'ultima sincronizzazione riuscita è precedente all'ultima seduta conclusa (test)
- [x] #5 Endpoint interno: 401 senza token o con token errato, disattivato se il token non è configurato, rate limit (test)
- [x] #6 Workflow GitHub Actions con cron nei giorni feriali, risveglio dell'istanza con retry, polling dello stato, job fallito se la run fallisce
- [x] #7 Tool MCP con blocco data_freshness (ultima sincronizzazione riuscita, stato, prezzi fermi) e un tool dedicato alla freschezza
- [x] #8 Calendari per borsa: fine settimana e festività non generano 'aggiornamento mancato'
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
MarketDataSyncService.run_sync unico per tutti i trigger (startup, external, scheduler, manual), con lock in-process e pg_try_advisory_xact_lock su una connessione dedicata. Passi estensibili: quotes (best effort), bars (dall'ultima barra per asset, max 30 giorni), fx. success solo se ogni asset quotabile ha la barra dell'ultima seduta conclusa della sua borsa; altrimenti partial/failed; last_successful_price_sync avanza solo su success. Tabelle market_data_sync_runs e market_data_asset_sync (migrazione 20261103_01, applicata anche all'avvio). Recupero all'avvio in thread se needs_sync (saltato se una run è finita nelle ultime 3 ore). Endpoint POST/GET /api/internal/market-data/sync[/status] con token Bearer (404 se non configurato, 401 se errato, rate limit). Workflow .github/workflows/market-data-sync.yml (lun-ven 22:40 UTC, mar-sab 06:15 UTC, manuale con force). MCP: blocco data_freshness in 15 tool e nuovo get_data_freshness. Test: test_task54_market_data_sync.py (34); 1020 passed; migrazione verificata su Postgres 16 locale. Aperto: un asset mai aggiornato dal provider rende ogni run partial.
<!-- SECTION:FINAL_SUMMARY:END -->
