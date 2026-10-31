---
id: TASK-27
title: 'Vista aggregata: scope globale e PortfolioSwitcher con multiselezione'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-31T10:00:00Z'
labels:
  - frontend
  - vista-aggregata
dependencies: [TASK-26]
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Uno scope di portafoglio condiviso da tutta l'app, al posto della selezione duplicata in ogni pagina: { mode: 'single', id } oppure { mode: 'aggregate', ids }, salvato in localStorage. Il PortfolioSwitcher permette di scegliere più portafogli con la stessa valuta base.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 PortfolioScopeContext con persistenza in localStorage (letture/scritture protette) e migrazione dalle chiavi esistenti (selectedPortfolioId, fireAggregatePortfolioIds)
- [x] #2 PortfolioSwitcher: sezione Vista aggregata con multiselezione limitata alla stessa valuta base, badge Aggregato (N), funziona anche nel BottomSheet mobile
- [x] #3 Hook in queries.ts guidati dallo scope: URL singolo o aggregate e query key che includono gli id ordinati
- [x] #4 Se un portafoglio dello scope viene eliminato lo scope si ripulisce; con un solo portafoglio rimasto torna in modalità single
- [x] #5 Test del context e dello switcher
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fase solo infrastruttura: nessuna pagina adotta ancora lo scope (TASK-28), il comportamento attuale delle pagine è invariato.

- **Tipo e helper** (`src/scope/portfolioScope.ts`): `PortfolioScope = { mode: 'single'; id } | { mode: 'aggregate'; ids }`, `PortfolioScopeInput = number | PortfolioScope | null | undefined`, `MAX_AGGREGATE_PORTFOLIOS = 20`. Helper: `normalizePortfolioIds` (interi positivi, anche stringhe numeriche, dedup + ordinati), `singleScope`, `aggregateScope` (un solo id → single, nessuno → null, max 20), `normalizeScope` (da JSON salvato o id), `toPortfolioScope`, `isAggregateScope`, `scopePortfolioIds`, `singlePortfolioId` (null per aggregato), `scopesEqual`, `portfolioScopeKey` (single → id nudo, aggregato → `'aggregate:1,2'`), `portfolioScopeKeyIncludes(key, id)` (per predicate di invalidazione), `scopePortfolios`, `resolveScopeBaseCurrency`, `portfoliosAvailableForAggregate`, `sanitizeScope` (id eliminati e valute diverse dal primo rimossi, uno → single, vuoto → primo portafoglio), `toggleScopePortfolio`.
- **Context** (`src/scope/PortfolioScopeContext.tsx`, montato in `App.tsx` attorno a `ProtectedApp`, dentro `AuthGuard`): `PortfolioScopeProvider`, `usePortfolioScope()` (errore fuori dal provider), `useOptionalPortfolioScope()`, `readStoredPortfolioScope()`. Valore: `scope`, `scopeKey`, `isAggregate`, `isReady` (lista portafogli caricata, scope sanificato), `portfolios`, `selectedPortfolios`, `baseCurrency`, `setScope`, `setSingle(id)`, `setAggregate(ids)`, `toggleInAggregate(id)`, `availableForAggregate(portfolios?)`.
  - Persistenza: nuova chiave `STORAGE_KEYS.portfolioScope` (`valore365.portfolioScope`, JSON dello scope); ogni accesso a localStorage in try/catch, JSON corrotto ignorato.
  - Migrazione (solo se la nuova chiave manca): selezione aggregata del FIRE (`fireAggregatePortfolioIds`, id stringa) se il FIRE era in modalità aggregata (`fireScopeMode === 'aggregate'`) con almeno 2 id, altrimenti `selectedPortfolioId` come single.
  - Compatibilità: i setter che portano a uno scope single scrivono anche `selectedPortfolioId`; la sanificazione no (non tocca la selezione propria delle pagine). Da rimuovere in TASK-28 insieme allo stato per pagina e alle chiavi FIRE.
  - Sanificazione derivata dalla query `['portfolios']` (`usePortfolios`): dopo un'eliminazione (refetch/invalidate della lista) lo scope si ripulisce e viene ri-salvato.
- **API** (`src/services/api/aggregate.ts`, esportato da `services/api`): `buildPortfolioIdsQuery(ids, params)`, `aggregatePath(resource, ids, params)`; funzioni `getAggregate*` per summary, positions, allocation, performers, timeseries, intraday-timeseries, transactions, data-coverage, performance summary/twr/twr timeseries/mwr/mwr timeseries/gain timeseries/monthly-returns/yearly/drawdown/rolling-windows/hall-of-fame, health, monte-carlo, stress-test, xray (decumulation esisteva già: `getAggregateDecumulationPlan`); wrapper `get*ForScope(scope, ...)` per ogni risorsa con una funzione singola esistente (per lo scope single chiamano la funzione singola, URL invariati). `getDecumulationPlanForScope` restituisce `DecumulationPlanResponse | AggregateDecumulationPlanResponse`. Tipi: `portfolio_ids?: number[] | null` sulle risposte con `portfolio_id`, `TransactionListItem.portfolio_name?`, `PerformancePeriod`.
- **Hook** (`components/dashboard/hooks/queries.ts`): tutti gli hook di portafoglio accettano `PortfolioScopeInput` (i chiamanti attuali passano un id e non cambiano); seconda parte della query key = `portfolioScopeKey(scope)`, quindi le key single restano `['portfolio-summary', 3]` (invalidazioni esistenti invariate) e gli aggregati non condividono mai la cache. Nuovi: `useDecumulationPlanForScope`, `usePortfolioTransactions` (key `['portfolio-transactions', scopeKey]`). Gli hook per-portafoglio senza rotta aggregata (target allocation, target performance, intraday target, intraday detail) restano disabilitati con uno scope aggregato; `useBenchmarkPrices` usa il primo id dello scope per il backfill. Differenza minima: un id non valido (NaN/0) ora lascia la query disabilitata invece di chiamare `/portfolios/NaN/...`.
- **PortfolioSwitcher**: nuove prop opzionali `allowAggregate` (default false → comportamento identico), `scope`, `onScopeChange`, `aggregateTotalValue`. Con `allowAggregate`: sezione "Vista aggregata" con checkbox (stessa valuta base, le altre disabilitate con "Valuta X: non aggregabile con Y", limite 20, l'ultimo non deselezionabile), badge "Aggregato (N)" su trigger desktop e chip mobile, totale e nomi nel trigger, pulsante "Torna a un solo portafoglio", la scelta dalla lista chiama `onChange` + `onScopeChange(single)`. Le azioni rapide (modifica/clona/elimina/...) compaiono solo in modalità single. Funziona nel BottomSheet mobile (stessa lista).
- Per TASK-28: in `useDashboardRefresh` il predicate confronta `queryKey[1] === portfolioId`; per lo scope aggregato usare `portfolioScopeKeyIncludes`.
- Test: `src/scope/portfolioScope.test.ts`, `src/scope/PortfolioScopeContext.test.tsx` (migrazione, sanificazione, eliminazione, localStorage che lancia eccezioni), `src/services/api/aggregate.test.ts` (URL), `src/components/dashboard/hooks/queries.test.tsx` (query key single vs aggregate), `src/components/portfolio/PortfolioSwitcher.test.tsx` (default invariato, multiselezione, valute disabilitate, mobile).
<!-- SECTION:NOTES:END -->
