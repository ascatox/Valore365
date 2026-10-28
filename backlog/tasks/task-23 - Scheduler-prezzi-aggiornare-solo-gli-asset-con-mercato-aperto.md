---
id: TASK-23
title: 'Scheduler prezzi: aggiornare solo gli asset con mercato aperto'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-28T06:55:00Z'
updated_date: '2026-10-28T07:14:00Z'
labels:
  - backend
  - pricing
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Lo scheduler aggiorna i prezzi ogni 60 secondi 24 ore su 24, anche di notte e nel weekend quando le quotazioni non cambiano: sono richieste inutili verso Yahoo che contribuiscono al rate limit. Il job in background salta gli asset il cui mercato è chiuso, ricavando la borsa dal suffisso del simbolo Yahoo (orari regolari nel fuso locale, weekend chiuso, crypto 24/7, FX 24/5, margine dopo la chiusura per catturare il prezzo d'asta). I refresh manuali dalle API non vengono filtrati. Le festività di borsa sono fuori scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Solo il job PriceRefreshScheduler._run_refresh filtra gli asset; i refresh manuali dalle API restano invariati
- [x] #2 Il mercato è ricavato dal suffisso del simbolo Yahoo: borse europee con fuso e orari locali, nessun suffisso = USA (09:30-16:00 New York), .T/.AX e altre borse note
- [x] #3 Weekend chiuso tranne crypto (24/7), FX 24/5, indici ^ per borsa se noti; suffisso sconosciuto = l'asset viene aggiornato (fail open)
- [x] #4 Margine configurabile dopo la chiusura (default 30 minuti) per catturare il prezzo d'asta
- [x] #5 Configurabile con PRICE_SCHEDULER_MARKET_HOURS_ONLY e PRICE_SCHEDULER_AFTER_CLOSE_GRACE_MINUTES (config.py e .env.example)
- [x] #6 Log del numero di asset saltati per mercato chiuso; se tutti i mercati sono chiusi il run non fa nessuna chiamata al provider
- [x] #7 Test: aperto/chiuso/margine/weekend per regione, cambio dell'ora legale, crypto 24/7, suffisso sconosciuto, scheduler filtrato e refresh manuale non filtrato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Nuovo modulo puro `app/services/market_hours.py`: `is_market_open(symbol, now, after_close_grace_minutes)` e `market_session_for_symbol(symbol)`. Suffissi europei con fuso e orario continuo locale (asta di chiusura compresa dove nota): .MI .DE .PA .AS .BR .LS .IR .MC .VI .HE .OL .ST .CO .SW .L .IL .AT .WA; borse regionali tedesche .F .SG .BE .DU .HM .HA .MU 08:00-22:00 Berlino; nessun suffisso = USA 09:30-16:00 New York; .T, .AX, .HK, .SI, .TO, .V; indici ^ principali per borsa (^GSPC, ^N225, ^GDAXI, ...). Crypto (BASE-USD/EUR/...) 24/7, le classi di azioni USA (BRK-B) restano USA; =X e =F 24/5 (da domenica 17:00 a venerdì 17:00 New York); weekend chiuso; ISIN, suffisso o indice sconosciuto = aperto (fail open). Il margine dopo la chiusura vale anche per FX il venerdì.
`PriceIngestionService.refresh_prices(market_hours_at=...)` salta gli asset con mercato chiuso (dopo lo skip degli ISIN non prezzabili) e logga numero e simboli saltati; se tutti sono chiusi non fa nessuna chiamata get_quote. Solo `PriceRefreshScheduler._run_refresh` passa `datetime.now(UTC)`, e solo con `PRICE_SCHEDULER_MARKET_HOURS_ONLY` (default true); le route di refresh manuale non passano il parametro.
Nuove impostazioni in config.py e .env.example: `PRICE_SCHEDULER_MARKET_HOURS_ONLY=true`, `PRICE_SCHEDULER_AFTER_CLOSE_GRACE_MINUTES=30`.
Il mercato è ricavato dal simbolo mappato in `asset_provider_symbols` (nuovo campo `PricingAsset.market_symbol` = `coalesce(aps.provider_symbol, a.symbol)`), non dal simbolo chiesto a Yahoo: lo scheduler usa `prefer_symbol_then_isin=True`, cioè `assets.symbol` prima del mapping, quindi un asset europeo salvato senza suffisso (es. VWCE nel seed, mappato su VWCE.MI) verrebbe altrimenti filtrato con orari USA. Che lo scheduler chieda a Yahoo il simbolo nudo (VWCE) invece di VWCE.MI è un comportamento preesistente della query, da valutare a parte.
Limiti: festività di borsa non gestite; fondi USA (NAV pubblicato dopo le 18:00 ET) aggiornati dallo scheduler il mattino dopo; .SG trattato come Stoccarda (su Yahoo Singapore è .SI, mentre il commento in `_EXCHCODE_TO_YAHOO` indica Singapore).
Verifica: tests/unit/test_market_hours.py (46 casi: aperto/chiuso/margine/weekend per regione, cambio ora legale USA ed europeo, crypto, FX/future, indici, fail open, now naive) e in test_pricing_service.py filtro attivo, tutti chiusi senza chiamate, refresh manuale non filtrato, job dello scheduler con orologio fermo al sabato e con il filtro disattivato. Unit 388 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Lo scheduler prezzi aggiorna solo gli asset la cui borsa è aperta (o ha chiuso da meno di 30 minuti, per catturare il prezzo d'asta). La borsa si ricava dal suffisso del simbolo Yahoo con fuso e orari locali; crypto 24/7, cambi e future 24/5, weekend chiuso, simboli sconosciuti sempre aggiornati. I refresh manuali dalle API non sono filtrati.

Logica in un modulo puro e testato (app/services/market_hours.py), filtro applicato da refresh_prices solo quando lo scheduler passa l'istante corrente; configurabile con PRICE_SCHEDULER_MARKET_HOURS_ONLY e PRICE_SCHEDULER_AFTER_CLOSE_GRACE_MINUTES. Con tutti i mercati chiusi un giro dello scheduler non fa chiamate a Yahoo. Festività non gestite. Gli asset salvati senza suffisso sono filtrati con gli orari della borsa del simbolo mappato (VWCE → VWCE.MI → Milano).
<!-- SECTION:FINAL_SUMMARY:END -->
