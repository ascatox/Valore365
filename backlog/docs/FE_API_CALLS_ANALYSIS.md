# Analisi API Chiamate dal Frontend

Questa analisi elenca le API **effettivamente chiamate dal FE**, con esclusione esplicita del file `src/frontend/valore-frontend/src/services/api.ts` nella ricerca.

## Tabella API chiamate

| API | File FE (linea chiamata) |
|---|---|
| `backfillPortfolioDailyPrices` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:251` |
| `cancelCsvImport` | `src/frontend/valore-frontend/src/components/portfolio/CsvImportModal.tsx:39` |
| `clonePortfolio` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:614` |
| `commitCsvImport` | `src/frontend/valore-frontend/src/components/portfolio/CsvImportModal.tsx:67` |
| `commitPortfolioRebalance` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:932` |
| `confirmPacExecution` | `src/frontend/valore-frontend/src/components/portfolio/PacSection.tsx:96` |
| `createCashMovement` | `src/frontend/valore-frontend/src/components/portfolio/CashSection.tsx:96` |
| `createPacRule` | `src/frontend/valore-frontend/src/components/portfolio/PacRuleDrawer.tsx:128` |
| `createPortfolio` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:551` |
| `createTransaction` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:813` |
| `deletePacRule` | `src/frontend/valore-frontend/src/components/portfolio/PacSection.tsx:123` |
| `deletePortfolio` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:590` |
| `deletePortfolioTargetAllocation` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:710` |
| `deleteTransaction` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:843` |
| `discoverAssets` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:407`, `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:437`, `src/frontend/valore-frontend/src/components/portfolio/TargetAllocationCsvImportModal.tsx:151`, `src/frontend/valore-frontend/src/components/portfolio/TargetAllocationCsvImportModal.tsx:230` |
| `ensureAsset` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:647`, `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:753`, `src/frontend/valore-frontend/src/components/portfolio/TargetAllocationCsvImportModal.tsx:276` |
| `getAdminPortfolios` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:75`, `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:253` |
| `getAssetLatestQuote` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:734` |
| `getGainTimeseries` | `src/frontend/valore-frontend/src/components/dashboard/analysis/PerformanceMetrics.tsx:86` |
| `getMarketQuotes` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useMarketData.ts:28` |
| `getPendingPacExecutions` | `src/frontend/valore-frontend/src/components/portfolio/PacSection.tsx:75`, `src/frontend/valore-frontend/src/components/portfolio/PacSection.tsx:101`, `src/frontend/valore-frontend/src/components/portfolio/PacSection.tsx:113` |
| `getPerformanceSummary` | `src/frontend/valore-frontend/src/components/dashboard/analysis/PerformanceMetrics.tsx:84` |
| `getPortfolioAllocation` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:119`, `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:138` |
| `getPortfolioCashBalance` | `src/frontend/valore-frontend/src/components/portfolio/CashSection.tsx:72`, `src/frontend/valore-frontend/src/components/portfolio/CashSection.tsx:101` |
| `getPortfolioDataCoverage` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:121` |
| `getPortfolioPacRules` | `src/frontend/valore-frontend/src/components/portfolio/PacSection.tsx:74`, `src/frontend/valore-frontend/src/components/portfolio/PacSection.tsx:125` |
| `getPortfolioPositions` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:118`, `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:137` |
| `getPortfolioRebalancePreview` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:885` |
| `getPortfolioSummary` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:117`, `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:136` |
| `getPortfolioTargetAllocation` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:114`, `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:241` |
| `getPortfolioTargetAssetIntradayPerformance` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:169` |
| `getPortfolioTargetAssetPerformance` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:116` |
| `getPortfolioTargetIntradayPerformance` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:158`, `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:397` |
| `getPortfolioTargetPerformance` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:115` |
| `getPortfolioTimeseries` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:120`, `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:139` |
| `getPortfolioTransactions` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:247` |
| `getTWRTimeseries` | `src/frontend/valore-frontend/src/components/dashboard/analysis/PerformanceMetrics.tsx:85` |
| `getUserSettings` | `src/frontend/valore-frontend/src/pages/Settings.page.tsx:43` |
| `refreshPortfolioPrices` | `src/frontend/valore-frontend/src/components/dashboard/hooks/useDashboardData.ts:250` |
| `skipPacExecution` | `src/frontend/valore-frontend/src/components/portfolio/PacSection.tsx:111` |
| `updatePacRule` | `src/frontend/valore-frontend/src/components/portfolio/PacRuleDrawer.tsx:113` |
| `updatePortfolio` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:566` |
| `updateTransaction` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:1018` |
| `updateUserSettings` | `src/frontend/valore-frontend/src/pages/Settings.page.tsx:82` |
| `uploadCsvImportPreview` | `src/frontend/valore-frontend/src/components/portfolio/CsvImportModal.tsx:52` |
| `upsertPortfolioTargetAllocation` | `src/frontend/valore-frontend/src/pages/Portfolio.page.tsx:690`, `src/frontend/valore-frontend/src/components/portfolio/TargetAllocationCsvImportModal.tsx:289` |

## Nota

Fuori da `api.ts` non risultano chiamate HTTP dirette (`fetch`, `axios`, ecc.): il FE usa i wrapper importati da `services/api`.
