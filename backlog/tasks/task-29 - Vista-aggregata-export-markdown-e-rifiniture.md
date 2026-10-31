---
id: TASK-29
title: 'Vista aggregata: export markdown e rifiniture'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T10:00:00Z'
labels:
  - backend
  - frontend
  - vista-aggregata
dependencies: [TASK-28]
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Completare la vista aggregata con l'export markdown, gli stati vuoti e la documentazione.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Export markdown aggregato (endpoint e azione nello switcher)
- [x] #2 Stati vuoti e messaggi chiari (es. portafogli con valute diverse non selezionabili, spiegazione della sola lettura)
- [x] #3 README/docs aggiornati con la descrizione della vista aggregata
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- **Backend – export Markdown aggregato**: `GET /api/portfolios/aggregate/export/markdown?portfolio_ids=…` in `routes_aggregate.py` (stessa dipendenza `require_auth_rate_limited`, `PlainTextResponse` `text/markdown`, `Content-Disposition` `valore365-aggregato-<data>.md`, errori via `aggregate_error`: vuoto/valute diverse/>20 → 400 `invalid_request`, non trovato → 404 `not_found`).
  - `app/services/portfolio_markdown_export.py`: `build_aggregate_portfolio_snapshot` (summary/posizioni da `get_summary_multi`/`get_positions_multi`, TER ponderato da `_load_holdings(ids)`, Doctor e Monte Carlo con la lista id, migliore/peggiore di giornata dalle posizioni fuse) e `build_aggregate_portfolio_markdown` (performance sui periodi con `PerformanceService` sulla lista id). `render_snapshot_markdown` con `snapshot["aggregate"]` intesta "Vista aggregata — Snapshot portafogli" + riga "Vista aggregata: A, B, C" e aggiunge in coda "Non inclusi nella vista aggregata" (scostamento dai target, PAC: dati per singolo portafoglio, mai letti). L'export singolo è invariato.
  - `app/copilot/snapshot.py`: estratti `doctor_snapshot` / `monte_carlo_snapshot` (stesso output), riusati dall'export aggregato.
- **Frontend – export**: `services/api/export.ts` ha `fetchMarkdownExport(path, fallback)` (errori come `ApiRequestError` con status/code); `getAggregatePortfolioMarkdown(ids)` e `getPortfolioMarkdownForScope(scope)` in `services/api/aggregate.ts`. `usePortfolioAiExport` accetta uno scope; nella pagina Portfolio l'export ("Esporta per AI" e azioni rapide "Copia per AI"/"Scarica .md" dello switcher) è riattivato anche in aggregato (prima disattivato in TASK-28). Nello switcher in aggregato restano solo le azioni rapide in sola lettura (Apri portfolio, Copia per AI, Scarica .md); Modifica/Clona/Elimina solo in singolo.
- **Stati vuoti e messaggi**:
  - Switcher: con un solo portafoglio, al posto della sezione aggregata, "servono almeno 2 portafogli con la stessa valuta base"; se nessun altro portafoglio ha la stessa valuta, avviso "Nessun altro portafoglio in EUR…". Il badge "Aggregato (N)" (trigger, chip mobile, intestazione sezione) ha un tooltip che spiega la sola lettura.
  - Zero posizioni in aggregato: Dashboard › Posizioni "Nessuna posizione nei portafogli selezionati." (`HoldingsTable.emptyMessage`), Doctor con avviso dedicato.
  - Errori di scope: `scope/aggregateErrors.ts` (`aggregateScopeErrorKind`, `friendlyAggregateError`, `pageQueryError`, `isAggregateQueryKey`). Il `PortfolioScopeProvider` ascolta la QueryCache: un errore di scope (404 "Portfolio non trovato", 400 valute diverse/vuoto/>20) su una query aggregata imposta `scopeNotice` (messaggio italiano) e rinfresca `['portfolios']` una sola volta per chiave di scope (nessun loop): la sanificazione riporta lo scope a single se resta un portafoglio. `reportScopeError` per le richieste fuori React Query (export, transazioni della pagina Portfolio). `AggregateScopeNotice` (Alert chiudibile) su Dashboard, Portfolio, Doctor, FIRE; i messaggi grezzi dell'API per errori di scope non sono più mostrati nelle pagine.
- **Docs**: sezione "Vista aggregata" nel README (selezione, stessa valuta, max 20, sola lettura, cosa non è disponibile, pattern API). `docs/` non ha pagine funzionalità.
- **Test**: backend `tests/unit/test_portfolio_markdown_export.py` (snapshot/markdown aggregato, sezioni omesse, zero posizioni, errori di scope), `tests/unit/test_routes_aggregate.py` (rotta, header, errori, ordine rotte). Frontend: `scope/aggregateErrors.test.ts`, `services/api/aggregate.test.ts` (URL/filename/errori export), `PortfolioSwitcher.test.tsx` (azioni rapide in aggregato, tooltip badge, 1 portafoglio, valute diverse), `Portfolio.aggregate.test.tsx` (copia/scarica aggregato, recupero dopo eliminazione, errore export), `Dashboard.aggregate.test.tsx` (zero posizioni, recupero valute diverse), `ScopePages.aggregate.test.tsx` (Doctor/FIRE). `pageHarness` accetta `Response` (errori) e un QueryClient esterno.
- Risultati: backend 493 passed (3 `test_backfill_*` falliti preesistenti); frontend 120 test verdi, eslint pulito, `tsc -b` 131 errori (baseline invariata), `vite build` ok.
<!-- SECTION:NOTES:END -->
