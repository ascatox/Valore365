---
id: TASK-24
title: 'Mercati: sezione notizie su borse e mercati internazionali'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-30T16:30:00Z'
updated_date: '2026-10-30T17:40:00Z'
labels:
  - backend
  - frontend
  - mercati
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
La tab Mercati mostra le notizie solo nel ticker scorrevole, difficile da leggere, e le prende da pochi simboli (S&P 500, Nasdaq, FTSE MIB, Bitcoin, oro), quasi tutte su Wall Street. Serve una piccola sezione con le notizie più rilevanti su borse e mercati internazionali: titolo, mercato di riferimento, breve sommario, fonte ed età della notizia.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Card "Notizie dai mercati" nella tab Mercati, sotto il calendario: le prime 6 notizie, il resto dietro "Mostra altre N"; stato di caricamento, errore e lista vuota
- [x] #2 Ogni notizia mostra badge del mercato (USA, Europa, Italia, Asia, Materie prime, Crypto), titolo con link esterno, sommario breve, fonte e "x fa"
- [x] #3 Le notizie arrivano da Google News RSS in italiano (una ricerca per mercato: USA, Europa, Italia, Asia, materie prime, crypto); se sono meno di 6 si aggiungono quelle della ricerca Yahoo per gli indici dei vari mercati, oro, petrolio e bitcoin
- [x] #4 Rilevanza: notizie più recenti, senza titoli duplicati, al massimo 4 per mercato finché gli altri mercati hanno notizie
- [x] #5 Date di pubblicazione in UTC (prima l'epoch era convertito nell'ora locale del server senza fuso)
- [x] #6 Link accettati solo http(s)
- [x] #7 Test backend (parsing dei due formati yfinance, selezione, route) e frontend (card)
- [x] #8 Rimosso il ticker scorrevole delle notizie, doppione della card
- [x] #9 Niente `yf.Ticker.news` (cookie e crumb Yahoo, rifiutati dai server: la card restava vuota); errori delle fonti nei log; un risultato vuoto resta in cache 60 secondi invece di 5 minuti
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Nuovo modulo `app/services/market_news.py`. `fetch_market_news` cerca su Google News RSS in italiano (`NEWS_QUERIES`, `when:2d`, hl=it/gl=IT) e, sotto `MIN_HEADLINES` = 6 notizie, aggiunge quelle della ricerca Yahoo `query1.finance.yahoo.com/v1/finance/search` per `NEWS_SYMBOLS` (^GSPC, ^IXIC, ^STOXX50E, ^GDAXI, FTSEMIB.MI, ^N225, GC=F, CL=F, BTC-USD): entrambe con httpx e User-Agent da browser, senza chiavi né crumb. Ogni fonte che fallisce viene loggata e saltata.
Prima versione con `yf.Ticker.news`: in produzione la card restava vuota. yfinance chiede le notizie a `finance.yahoo.com/xhr/ncp` con cookie e crumb, che Yahoo rifiuta agli IP dei server (stesso problema già noto per il calendario e per le quotazioni, TASK-22), e l'errore veniva ignorato senza log.
`parse_google_news_rss` toglie dal titolo il suffisso " - <fonte>" e usa `<source>` come editore; `parse_yahoo_article` legge sia il formato piatto sia quello sotto `content`, con sommario troncato a 280 caratteri; `select_relevant_news` deduplica i titoli, ordina per data (UTC) e limita a 4 le notizie per mercato finché gli altri mercati ne hanno. `MarketNewsItem` ha i nuovi campi opzionali `region` e `summary`. La route `/markets/news` tiene in cache 5 minuti (60 secondi se vuota) e accetta un `news_fetcher` iniettabile.
Frontend: `MarketNewsCard` (con `MarketNewsView` testabile) in `MercatiTab`; "x fa" in `formatTimeAgo` in formatters.ts. Rimosso il ticker scorrevole `NewsTicker`, che mostrava gli stessi titoli.
Verifica: tests/unit/test_market_news.py (16 casi: RSS Google, ricerca Yahoo con httpx.MockTransport, fallback, selezione, route e cache), MarketNewsCard.test.tsx (3 casi). Unit backend 405 passed, vitest 45 passed, tsc ed eslint puliti. Google News e Yahoo non sono raggiungibili dal container: nessuna prova con dati reali.
<!-- SECTION:NOTES:END -->
