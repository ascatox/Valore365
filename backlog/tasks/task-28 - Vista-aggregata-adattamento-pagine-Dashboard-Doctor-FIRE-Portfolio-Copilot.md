---
id: TASK-28
title: 'Vista aggregata: adattamento pagine Dashboard, Doctor, FIRE, Portfolio, Copilot'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T10:00:00Z'
labels:
  - frontend
  - vista-aggregata
dependencies: [TASK-27]
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Usare lo scope globale in tutte le pagine. Il FIRE abbandona la somma lato frontend e usa gli endpoint aggregati. La pagina Portfolio in vista aggregata è in sola lettura.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Dashboard e Doctor funzionano completamente in vista aggregata
- [x] #2 FIRE usa lo scope globale e gli endpoint aggregati; rimossa la logica di somma e la chiave fireAggregatePortfolioIds
- [x] #3 Portfolio: posizioni fuse e transazioni con colonna Portafoglio; disattivate con tooltip le azioni di scrittura (nuova transazione, ribilanciamento, target allocation, PAC, liquidità, CSV, modifica/clona/elimina)
- [x] #4 Copilot riceve portfolio_ids dello scope corrente
- [x] #5 Test delle pagine in modalità aggregata
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- **Scope condiviso**: Dashboard, Portfolio, Doctor e FIRE leggono `usePortfolioScope()`; rimossi lo stato `selectedPortfolioId` per pagina e le letture/scritture di `STORAGE_KEYS.selectedPortfolioId` in `Dashboard.page.tsx`, `Doctor.page.tsx`, `Fire.page.tsx`, `usePortfolioPage.ts`. Ogni `PortfolioSwitcher` ha `allowAggregate`, `scope`, `onScopeChange={setScope}`, `onChange → setSingle` e il totale aggregato. Il context continua a scrivere `selectedPortfolioId` sugli scope single (non più letto dalle pagine: solo compatibilità all'indietro) e la migrazione dalle vecchie chiavi resta.
  - `setScope` sanifica subito solo se tutti gli id sono nella lista caricata: un portafoglio appena creato/importato (lista non ancora rinfrescata) non fa più ricadere lo scope sul primo portafoglio; lo `scope` derivato è comunque sempre sanificato.
  - `usePortfolioPage.loadPortfolios` scrive la lista fresca in `['portfolios']` (`setQueryData`): dopo crea/elimina il context si sanifica e gli switcher delle altre pagine sono aggiornati.
- **Dashboard**: tab Panoramica, Posizioni, Performance passano lo scope agli hook (`scope` al posto di `portfolioId` in `PanoramicaTab`, `PosizioniTab`, `AnalisiTab`, `PerformanceMetrics`): summary, posizioni fuse, timeseries/intraday, performers, data coverage, benchmark, tutte le metriche di performance in aggregato. In aggregato: badge "Aggiornato" (da target-performance) assente; Posizioni senza colonna target (target allocation per portafoglio) e "Reclassifica tipi" disattivato con tooltip; tab Analisi (nascosto da flag) mostra "Non disponibile nella vista aggregata". Non ci sono sezioni PAC/esecuzioni pendenti in Dashboard.
  - `useDashboardRefresh(scope)`: aggiorna prezzi e storico di ogni portafoglio dello scope (in sequenza, contatori sommati) e invalida con `matchesRefreshedPortfolios` (`portfolioScopeKeyIncludes`): le query del singolo e di ogni aggregato che include uno dei portafogli. Anche "Aggiorna prezzi" in Posizioni aggiorna tutti i portafogli dello scope.
  - Nuovo `components/dashboard/hooks/invalidation.ts`: `PORTFOLIO_QUERY_PREFIXES`, `scopeKeyCoversAny`, `invalidatePortfolioQueries(queryClient, ids)`. Non esistevano altri predicate `queryKey[1] === portfolioId`; dopo ogni scrittura della pagina Portfolio (transazioni create/modificate/eliminate, ribilanciamento, import CSV — tutte passano da `loadTransactions(id)`) ora vengono invalidate le query del portafoglio e degli aggregati che lo includono (prima Dashboard/Doctor restavano vecchie fino allo staleTime).
- **Doctor**: health, summary, X-Ray, Monte Carlo, stress test sullo scope (`XRayCard`, `MonteCarloCard`, `StressTestCard` ricevono `scope`). In aggregato il referto è intestato "Vista aggregata (nomi)". Il decumulo non è nella pagina Doctor (è nel FIRE).
- **FIRE**: scope condiviso + endpoint aggregati (`usePortfolioSummary(scope)`, `useMonteCarloProjection(scope)`, `useDecumulationPlanForScope`). Rimossi: `useQueries` per portafoglio, somma `aggregateSummaries`, medie pesate di rendimento/volatilità e scenari sommati (ora un'unica proiezione Monte Carlo sulle holdings fuse, stesso calcolo degli scenari del singolo), stato `fireScopeMode`/`aggregatePortfolioIds`, SegmentedControl Portafoglio/Aggregato e modale "Perimetro FIRE" (il perimetro si sceglie dallo switcher), scritture di `fireScopeMode`/`fireAggregatePortfolioIds` (le chiavi restano in `STORAGE_KEYS` solo per la migrazione del context). Parametri, salvataggio, testi e accumulo invariati (`accumulation.test.ts` invariato e verde).
- **Portfolio (sola lettura in aggregato)**: transazioni da `/portfolios/aggregate/transactions` con colonna "Portafoglio" (desktop) e nome portafoglio nella riga/scheda mobile; filtro testo anche sul nome portafoglio; avviso "Vista aggregata in sola lettura". Disattivati con tooltip "Seleziona un solo portafoglio per modificare" (`scope/AggregateReadOnly.tsx`): Nuova transazione, Importa (CSV), Nuova regola PAC, modifica/elimina transazione (desktop; su mobile la scheda mostra il motivo al posto dei pulsanti), export per AI (tooltip dedicato). Liquidità e PAC sostituiti da "Non disponibile nella vista aggregata" (nessuna chiamata cash/PAC). Modifica/clona/elimina/export non passati allo switcher; le azioni rapide `?azione=` che scrivono sono ignorate; "Nuovo portafoglio" resta (non dipende dallo scope). Gli handler di scrittura di `usePortfolioPage` usano `writablePortfolioId` (null in aggregato) e escono subito: nessuna API di scrittura è raggiungibile. Target allocation e ribilanciamento non hanno UI nella pagina attuale (restano per singolo, disattivati in aggregato perché `selectedPortfolioId` è null).
  - Le posizioni fuse sono nella Dashboard (tab Posizioni): la pagina Portfolio non ha una vista posizioni nemmeno in modalità singola.
- **Copilot**: tutte le pagine passano `portfolioId` = primo id dello scope e `portfolioIds` = id dello scope in aggregato (`portfolio_ids` nel body di `/copilot/chat`). Lo storico conversazioni è separato per scope (`copilot_chat_aggregate_1_2`), non mescolato col primo portafoglio.
- **Mobile**: lo switcher (BottomSheet) è lo stesso su tutte le pagine; nel foglio "Azioni rapide" (`App.tsx`) Nuova transazione / Importa / Nuova regola PAC sono disattivate in aggregato con il motivo come descrizione.
- **Test**: `src/test/pageHarness.tsx` (pagine reali con `fetch` simulato che registra metodo e path), `pages/Dashboard.aggregate.test.tsx`, `pages/Portfolio.aggregate.test.tsx` (colonna Portafoglio, azioni disattivate con tooltip, nessuna scrittura, tab Liquidità/PAC, mobile, azioni rapide), `pages/ScopePages.aggregate.test.tsx` (Doctor e FIRE sugli endpoint aggregati senza richieste per portafoglio, decumulo aggregato, scope condiviso Dashboard → Doctor), `components/dashboard/hooks/useDashboardRefresh.aggregate.test.tsx` (predicate di refresh e `invalidatePortfolioQueries`), `components/copilot/CopilotChat.test.tsx` (`portfolio_ids` e storico per scope). Frontend: 101 test verdi, lint pulito, `tsc -b` 131 errori (baseline invariata), `vite build` ok. Nessuna modifica backend.
<!-- SECTION:NOTES:END -->
