# Valore365 — Backlog

> Generato il 2026-03-06. Aggiornare man mano che le voci vengono completate.

---

## P0 — Sicurezza & Stabilità

| # | Voce | Dettaglio | File principali |
|---|------|-----------|-----------------|
| 1 | Auth bypass in dev mode | `CLERK_AUTH_ENABLED` default `false` — aggiungere check che blocchi l'avvio in `APP_ENV=production` senza auth | `config.py`, `auth.py`, `main.py` |
| 2 | JWT audience non verificato | `verify_aud: False` nel decode — abilitare e configurare audience atteso | `auth.py:76` |
| 3 | Rate limiting globale | Nessun rate-limit su endpoint — introdurre `slowapi` o middleware custom | `main.py` |
| 4 | DoS `/prices/backfill-daily` | Fino a 2000 giorni × N asset in sequenza — aggiungere limiti e timeout | `main.py:522-545` |
| 5 | DoS `/markets/quotes` | 14 chiamate sequenziali con sleep — parallelizzare con limite concorrenza | `main.py:1204-1244` |
| 6 | Thread pool per task background | `threading.Thread()` senza limiti — sostituire con `ThreadPoolExecutor` | `main.py:453, 756, 1091` |
| 7 | Body size limit | Nessun limite dimensione request — aggiungere middleware (1 MB max) | `main.py` |
| 8 | CORS troppo permissivo | Regex `.*\.vercel\.app` — restringere al dominio effettivo | `main.py:131` |

---

## P1 — Tech Debt & Qualità

| # | Voce | Dettaglio | File principali |
|---|------|-----------|-----------------|
| 9 | Validazione input mancante | Campi `notes` senza `max_length`, CSV upload senza limite file | `models.py`, `csv_service.py` |
| 10 | Paginazione endpoint | `/transactions`, `/positions` restituiscono tutto — aggiungere cursor/offset | `repository.py`, `main.py` |
| 11 | Race condition rebalance | Richieste concorrenti creano transazioni conflittuali — aggiungere lock | `main.py:1040-1104` |
| 12 | Target allocation sum > 100% | Nessuna validazione sulla somma pesi — aggiungere check | `main.py`, `repository.py` |
| 13 | Log dati sensibili CSV | Dati finanziari utente loggati in plaintext a livello INFO | `csv_service.py:90, 211, 225` |
| 14 | Errori verbosi esposti | `RequestValidationError` mostra dettagli interni al client | `main.py:146` |
| 15 | Security headers mancanti | CSP, X-Frame-Options, HSTS, etc. | `nginx.prod.conf`, `index.html` |
| 16 | Dipendenze FE vulnerabili | `npm audit` segnala 5 CVE (build-time) — eseguire `npm audit fix` | `package.json` |

---

## P2 — Feature Incomplete / Da Implementare

| # | Voce | Dettaglio | Riferimento |
|---|------|-----------|-------------|
| 17 | Auto-refresh dashboard | Bottone aggiorna con modalità auto-refresh (ogni 60s) bloccabile/sbloccabile, lato FE | Richiesta utente |
| 18 | Auto-backfill prezzi | Backfill automatico singolo asset alla creazione transazione/target allocation | `docs/TASK.md` |
| 19 | Data coverage warning | Banner nel dashboard quando dati insufficienti per grafici | `docs/TASK.md` |
| 20 | CSV import miglioramenti | Rollback su errore parziale, progress tracking, messaggi errore migliori | `csv_service.py` |
| 21 | PAC UX miglioramenti | Validazione conflitti regole, preview esecuzione, audit trail | `PacRuleDrawer.tsx` |
| 22 | Ricerca asset avanzata | Filtri per asset class, exchange, volume minimo, watchlist/preferiti | `api.ts`, `main.py` |
| 23 | Esportazione dati CSV | Bottone "Esporta Dati in CSV" nella pagina Sicurezza non funzionante | `Settings.page.tsx:289` |
| 24 | Eliminazione dati utente | Bottone "Elimina tutti i dati" nella pagina Sicurezza non funzionante | `Settings.page.tsx:290-292` |
| 25 | Copilot: cronologia chat | Persistenza conversazioni, ripresa sessione precedente | `CopilotChat.tsx` |
| 26 | Copilot: streaming Gemini | Gemini restituisce risposta completa, non stream — usare `generate_content_stream` | `copilot_service.py:279-284` |

---

## P3 — Test & CI

| # | Voce | Dettaglio |
|---|------|-----------|
| 27 | Test frontend (zero coverage) | Configurare Vitest, test per hooks, utils, API calls |
| 28 | Test backend incompleti | Solo 3 file test — aggiungere repository, multi-tenant, CSV, performance |
| 29 | Test E2E | Considerare Playwright/Cypress per smoke test automatici |
| 30 | CI pipeline | GitHub Actions per lint, type-check, test su PR |

---

## P4 — UX & UI

| # | Voce | Dettaglio | Riferimento |
|---|------|-----------|-------------|
| 31 | Tab style: pills → underline | Tabs dashboard da "pills" a "underline" per UX più pulita | `docs/UI_UX_IMPROVEMENTS.md` |
| 32 | Posizioni raggruppate per asset class | Accordion rows con subtotali per classe | `docs/UI_UX_IMPROVEMENTS.md` |
| 33 | Delta target allocation in posizioni | Visualizzazione scostamento da target nella tabella posizioni | `docs/UI_UX_IMPROVEMENTS.md` |
| 34 | Y-axis labels sui grafici performance | Aggiungere tacche e label sugli assi Y | `docs/UI_UX_IMPROVEMENTS.md` |
| 35 | Tooltip per valori N/D | Spiegazione contestuale quando un KPI non è disponibile | `docs/UI_UX_IMPROVEMENTS.md` |
| 36 | Ottimizzazione mercati ultrawide | Grid mercati non sfrutta schermi larghi | `docs/UI_UX_IMPROVEMENTS.md` |
| 37 | Mobile: sticky header + CTA | Header fisso con portfolio switcher e bottoni azione | `docs/MOBILE_UI_IMPACT_PROPOSAL.md` |
| 38 | Mobile: bottom sheet azioni | Drawer dal basso per azioni frequenti (transazione, refresh) | `docs/MOBILE_UI_IMPACT_PROPOSAL.md` |
| 39 | Messaggi errore user-friendly | Mappare error code backend a messaggi italiani comprensibili | `api.ts:491-504` |

---

## P5 — Strategici / Futuri

| # | Voce | Dettaglio | Riferimento |
|---|------|-----------|-------------|
| 40 | SaaS billing & subscription | Integrazione pagamenti, tier freemium | `docs/SAAS_MARKETPLACE_INCREMENTAL_PLAN.md` |
| 41 | Marketplace template/allocazioni | Condivisione allocation model tra utenti | `docs/SAAS_MARKETPLACE_INCREMENTAL_PLAN.md` |
| 42 | AI Advisor agent avanzato | Analisi proattiva, alert, raccomandazioni | `docs/PIANO_AI_ADVISOR_AGENT.md` |
| 43 | Twelve Data integration | Provider alternativo a yfinance per dati più affidabili | `docs/ARCHITECTURE_TWELVEDATA.md` |
| 44 | Scheduler distribuito | APScheduler single-instance → Celery per multi-worker | `scheduler.py` |
| 45 | Caching strategy | HTTP cache headers, ETags, query result caching | Generale |
| 46 | Deployment runbook | Guida step-by-step deploy/rollback/monitoring | Mancante |

---

## Legenda priorità

- **P0**: Bloccanti per produzione — sicurezza e stabilità
- **P1**: Tech debt che impatta qualità e manutenibilità
- **P2**: Feature richieste o incomplete
- **P3**: Test e CI/CD
- **P4**: UX/UI polish
- **P5**: Strategici a medio-lungo termine
