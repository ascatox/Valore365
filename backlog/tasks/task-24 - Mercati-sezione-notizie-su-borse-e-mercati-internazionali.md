---
id: TASK-24
title: 'Mercati: sezione notizie su borse e mercati internazionali'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-30T16:30:00Z'
updated_date: '2026-10-30T16:55:00Z'
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
- [x] #3 Le notizie arrivano da indici di USA, Europa, Italia e Asia, oltre a oro, petrolio e bitcoin
- [x] #4 Rilevanza: notizie più recenti, senza titoli duplicati, al massimo 4 per mercato finché gli altri mercati hanno notizie
- [x] #5 Date di pubblicazione in UTC (prima l'epoch era convertito nell'ora locale del server senza fuso)
- [x] #6 Link accettati solo http(s)
- [x] #7 Test backend (parsing dei due formati yfinance, selezione, route) e frontend (card)
- [x] #8 Rimosso il ticker scorrevole delle notizie, doppione della card
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Nuovo modulo `app/services/market_news.py`: `parse_yahoo_article` legge sia il formato piatto di `yf.Ticker.news` sia quello annidato sotto `content` (yfinance >= 0.2.50: provider.displayName, canonicalUrl/clickThroughUrl, pubDate, summary), sommario troncato a 280 caratteri; `select_relevant_news` deduplica i titoli, ordina per data e limita le notizie per mercato; `fetch_yahoo_news` scarica fino a 6 articoli per simbolo.
`NEWS_SYMBOLS` diventa una lista (simbolo, mercato): ^GSPC, ^IXIC, ^STOXX50E, ^GDAXI, FTSEMIB.MI, ^N225, GC=F, CL=F, BTC-USD. `MarketNewsItem` ha i nuovi campi opzionali `region` e `summary`. La route `/markets/news` mantiene la cache di 5 minuti e accetta un `news_fetcher` iniettabile per i test.
Frontend: `MarketNewsCard` (con `MarketNewsView` testabile) in `MercatiTab`; il calcolo "x fa" è in `formatTimeAgo` in formatters.ts. Il ticker scorrevole delle notizie (`NewsTicker`) è rimosso: mostrava gli stessi titoli della card.
Verifica: tests/unit/test_market_news.py (9 casi), MarketNewsCard.test.tsx (3 casi). Unit backend 398 passed, vitest 45 passed, tsc ed eslint puliti. Yahoo non raggiungibile dal container: nessuna prova con dati reali.
<!-- SECTION:NOTES:END -->
