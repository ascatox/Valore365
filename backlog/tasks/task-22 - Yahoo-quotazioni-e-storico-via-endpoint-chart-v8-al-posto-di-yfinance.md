---
id: TASK-22
title: 'Yahoo: quotazioni e storico via endpoint chart v8 al posto di yfinance'
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
Ogni YahooFinanceClient.get_quote passa da fast_info di yfinance: last_price scarica un anno di storico giornaliero solo per leggere l'ultimo prezzo e previous_close scarica lo storico orario di 5 giorni (con fallback su ticker.info, la chiamata più limitata da Yahoo). Lo scheduler prezzi lo chiama ogni 60 secondi per ogni asset, in sequenza: sugli IP condivisi di Render Yahoo risponde con rate limit. Le chiamate frequenti (quotazioni, quotazioni mercati, storico giornaliero, intraday, cambi FX) passano a una sola richiesta httpx all'endpoint v8/finance/chart, con client condiviso e retry su 429/5xx, mantenendo interfaccia e semantica attuali (prezzi rettificati come auto_adjust=True, date nel fuso della borsa, previous close = penultima chiusura giornaliera). yfinance resta solo per ricerca simboli, .info e top holdings ETF, chiamate rare. Il refresh prezzi esegue le quotazioni con parallelismo controllato.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 get_quote, get_market_quote, get_daily_bars, get_intraday_bars e get_daily_fx_rates fanno una sola richiesta GET a v8/finance/chart, senza yfinance né pandas
- [x] #2 Interfaccia e tipi di ritorno di YahooFinanceClient invariati; yfinance resta solo per search_symbols, get_asset_info e get_etf_top_holdings
- [x] #3 Barre giornaliere rettificate per split e dividendi (adjclose/close) e datate nel fuso della borsa; end esclusivo e order rispettati
- [x] #4 previous_close = penultima chiusura giornaliera non nulla, con fallback su chartPreviousClose se ci sono meno di 2 barre
- [x] #5 Client httpx condiviso e thread-safe, User-Agent da browser, timeout configurato, retry con backoff su 429/5xx che rispetta Retry-After
- [x] #6 Errori Yahoo (404 / chart.error) diventano ProviderError no_data; valori source e flag di fallback compatibili con il frontend
- [x] #7 refresh_prices esegue le quotazioni in parallelo (FINANCE_QUOTE_CONCURRENCY), in sequenza se FINANCE_SYMBOL_REQUEST_DELAY_SECONDS > 0, con un solo save_price_ticks e ordine stabile
- [x] #8 Test offline con httpx.MockTransport: parsing quotazione, previous close, barre rettificate, fuso della borsa (caso ^N225), righe nulle, 404, retry 429 con Retry-After, simbolo FX
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Percorso nuovo: `YahooFinanceClient._fetch_chart` fa una sola GET a `query1.finance.yahoo.com/v8/finance/chart/{symbol}` (simbolo URL-encoded, User-Agent da browser, timeout configurato) con retry su 429/5xx/errori di rete tramite `_compute_retry_delay` (Retry-After rispettato; oltre 10 s si rinuncia subito per non tenere fermo un thread). `FINANCE_MAX_RETRIES` resta il numero totale di tentativi, come prima per YahooFinanceClient.
Errori: `_chart_result` mappa 404 e `chart.error` su ProviderError `no_data` con i messaggi italiani di prima; 401/403 (crumb, blocco IP) su `provider_error`; JSON non valido su `invalid_payload`. `is_unpriceable_on_yahoo` invariato.
Client httpx condiviso a livello di modulo (creazione sotto lock), perché `make_finance_client` viene chiamato per richiesta; iniettabile nel costruttore (`http_client=`) per i test.
Quotazioni: una richiesta `range=5d&interval=1d`. Prezzo = `meta.regularMarketPrice` (se manca: ultima chiusura, source `history_close`, ts = mezzanotte locale come l'indice yfinance). previous_close = penultima chiusura giornaliera non nulla dopo il dedup per giorno di borsa (la riga "live" di Yahoo sostituisce la precedente), `chartPreviousClose` solo con meno di 2 barre. get_quote tiene `ts=now(UTC)` (price_ticks e day change usano `ts::date`); get_market_quote usa `regularMarketTime` e non solleva mai. Etichette `fast_info`/`history_close` e warning invariati perché `dataQuality.ts` del frontend li traduce.
Storico e FX: period1/period2 = start/end a mezzanotte UTC con un giorno di margine per lato, poi filtro [start, end) sulle date nel fuso della borsa (`meta.exchangeTimezoneName` con ZoneInfo): stessa semantica di yfinance senza la sua richiesta extra per il fuso. OHLC moltiplicati per adjclose/close, close = adjclose, volume null = 0 (yfinance fa fillna(0)); senza serie adjclose valori grezzi; righe con null saltate; stamp 22:00/23:00 riportati al giorno dopo (fix_Yahoo_dst_issue). `order=desc` rispettato, `outputsize` ignorato come prima. Simbolo FX `{FROM}{TO}=X`.
Intraday: range/interval passati a Yahoo, timestamp tz-aware nel fuso della borsa, riga live fusa nella barra dell'intervallo in corso come fa yfinance; `no_data` = lista vuota.
ISIN usato come simbolo: risolto con `yf.Search` come faceva `yf.Ticker`, con cache in memoria.
pricing_service: `_fetch_quotes` usa un ThreadPoolExecutor (`FINANCE_QUOTE_CONCURRENCY`, default 4), sequenziale con pausa se `FINANCE_SYMBOL_REQUEST_DELAY_SECONDS > 0`; risultati nell'ordine degli asset e un solo `save_price_ticks`.
Richieste: get_quote da almeno 2 (history 1y giornaliera + 5d oraria prepost, più `.info` se previous_close falliva) a 1 con 5 barre; get_market_quote da 2 a 1; storico, intraday e FX restano 1 ma senza pandas e senza crumb/lookup del fuso.
Verifica: unit 388 passed (baseline 308 passed), integration 34 passed (baseline 34). Test offline con httpx.MockTransport e payload chart realistici; 10 mutazioni del codice nuovo (rettifica, fuso, previous close, dedup, Retry-After, end escluso, fix DST, 404, parallelismo, filtro mercati) tutte rilevate dai test.
Non verificato contro l'API reale (rete verso Yahoo bloccata nel container): da controllare in staging che il chart v8 risponda all'User-Agent httpx senza crumb (dal 2025 Yahoo fa fingerprint TLS e yfinance usa curl_cffi), che adjclose arrivi con period1/period2, e le date delle barre di ^N225 e dei cambi.
Differenze semantiche: per i titoli USA previous_close ora è la chiusura ufficiale della sessione precedente (fast_info usava l'ultimo prezzo after-hours delle barre orarie prepost); errori di rete e 429 ora hanno reason timeout/rate_limited/provider_error invece di no_data; 401/403 non sono più no_data; le barre intraday pre/post non richieste non sono filtrate con tradingPeriods e 30m non viene ricampionato (nessun chiamante li usa).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Le chiamate frequenti di YahooFinanceClient (get_quote, get_market_quote, get_daily_bars, get_intraday_bars, get_daily_fx_rates) non passano più da yfinance: ognuna fa una sola GET httpx all'endpoint chart v8, con client condiviso e thread-safe, User-Agent da browser e retry su 429/5xx che rispetta Retry-After. Interfaccia, tipi di ritorno, etichette source e messaggi di errore restano quelli di prima; yfinance resta per ricerca simboli, .info e top holdings ETF.

Semantica preservata: barre rettificate come auto_adjust=True, date nel fuso della borsa (incluso ^N225), end escluso, previous_close = penultima chiusura giornaliera, ts del price tick = ora del refresh. Il refresh prezzi scarica le quotazioni in parallelo (FINANCE_QUOTE_CONCURRENCY=4), in sequenza se è configurata una pausa tra simboli.

Una quotazione passa da almeno 2 richieste pesanti (un anno di storico giornaliero + 5 giorni orari, a volte quoteSummary) a 1 richiesta di 5 barre. Unit 388 passed (baseline 308), integration 34/34. Da verificare in staging contro Yahoo reale: risposta del chart v8 all'User-Agent httpx senza crumb, presenza di adjclose, date di ^N225 e FX.
<!-- SECTION:FINAL_SUMMARY:END -->
