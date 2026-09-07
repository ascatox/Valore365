---
title: "Scheda rendiconto portafoglio (profilo dichiarato, orizzonte, periodo)"
status: "To Do"
priority: "high"
created: 2026-09-07
labels: ["performance", "backend", "frontend", "feature", "rendiconto"]
---

# Scheda rendiconto portafoglio

## Contesto

Obiettivo: rispondere in modo completo alla domanda "che rendimenti ha generato il mio portafoglio?", allo stesso livello dei rendiconti dei consulenti finanziari, che mostrano in un colpo d'occhio: data inizio rapporto, profilo di rischio, orizzonte temporale, periodo di riferimento e rendimento (MWR).

Stato attuale verificato:

- **Rendimento MWR**: già presente e corretto. `mwr_pct` è il rendimento cumulato di periodo, `mwr_annualized_pct` l'annualizzato per periodi >= 1 anno.
- **Data inizio rapporto**: risolto separatamente — `get_portfolio_inception_date` usa la data della prima transazione invece di `portfolios.created_at`.
- **Profilo di rischio**: esiste solo *calcolato* dalla volatilità (`portfolio_doctor/_health.py:735-746`, scala low/medium/high). Il questionario `CreatorProfileQuiz.tsx` vive in `useState` e non viene mai inviato al backend.
- **Orizzonte temporale**: assente dal modello dati. Esistono solo `PROJECTION_HORIZONS = [5, 10, 20]` hardcoded (`_monte_carlo.py:25`) e le età FIRE, che sono per-utente e non per-portafoglio.
- **Periodo di riferimento**: il backend accetta `start_date`/`end_date` arbitrari su tutti gli endpoint di performance **tranne** `/performance/summary`, vincolato ai preset dalla regex in `routes_analytics.py:61`. Il frontend non ha alcun date picker (nessun `@mantine/dates` fra le dipendenze) e non mostra mai `start_date`/`end_date`, che il summary già restituisce: l'unico intervallo visibile a schermo è quello della heatmap mensile (`PerformanceMetrics.tsx:171-172`).

### Bug collegato: KPI e grafici usano finestre diverse

In `PerformanceMetrics.tsx` la card KPI e i grafici sottostanti chiedono lo **stesso periodo** ma per due strade diverse:

- `usePerformanceSummary(portfolioId, period)` (riga 35) manda il preset al backend, che lo risolve con `_PERIOD_TO_DAYS` — giorni fissi: `1m`=30, `3m`=90, `6m`=180, `3y`=1095;
- tutti gli altri hook (righe 36-42) ricevono `startDate = periodToStartDate(period)` (riga 32), calcolato lato client con **mesi di calendario** (`utils.ts:28-42`).

Le due finestre non coincidono. Misurato al 2026-09-07:

| periodo | client (grafici) | backend (KPI) | scarto |
|---|---|---|---|
| 1m | 2026-08-07 | 2026-08-08 | 1 giorno |
| 3m | 2026-06-07 | 2026-06-09 | 2 giorni |
| 6m | 2026-03-07 | 2026-03-11 | **4 giorni** |
| 1y | 2025-09-07 | 2025-09-07 | 0 |
| 3y | 2023-09-07 | 2023-09-08 | 1 giorno |

Il TWR/MWR mostrato nella card e la curva del grafico si riferiscono quindi a periodi leggermente diversi. Va risolto **insieme** al periodo personalizzato, perché è la stessa area di codice: una volta che il frontend sa mandare `start_date`/`end_date` espliciti al summary, la risoluzione del periodo deve avvenire in un solo posto (preferibilmente il backend, che è già la fonte di verità per `all` e per il clamp all'inception) ed essere riusata da tutte le query.

## Obiettivo

Una scheda "Rendiconto" che riunisca le cinque informazioni, con un valore aggiunto rispetto ai rendiconti tradizionali: il confronto fra profilo di rischio **dichiarato** e rischio **effettivo** del portafoglio.

## Scope

### 1. Profilo di rischio e orizzonte dichiarati (persistiti)

- Nuovi campi a livello di **portafoglio** (non di utente: portafogli diversi hanno scopi diversi): profilo di rischio su scala 1-4 e orizzonte temporale (es. `< 3 anni`, `3-5 anni`, `> 5 anni`).
- Migrazione SQL in `database/migrations/`, colonne sulla tabella `portfolios`.
- Attenzione ai punti di modifica noti: `repository/_portfolio_crud.py` elenca esplicitamente le colonne in 6 punti (SELECT/INSERT/UPDATE), e i modelli sono in `models.py:65-93` (`PortfolioCreate`, `PortfolioUpdate`, `PortfolioRead`).
- Riusare come base le domande già scritte in `components/creator/CreatorProfileQuiz.tsx:14-33`, rendendole persistenti.

### 2. Confronto dichiarato vs effettivo

- Nella scheda, affiancare il profilo dichiarato al `risk_level` calcolato dal Doctor ed evidenziare lo scostamento (es. "dichiarato Bilanciato, il portafoglio si comporta da Aggressivo").
- Serve una mappatura esplicita fra la scala dichiarata (1-4) e quella calcolata (`low`/`medium`/`high`/`unknown`), da definire in un solo punto e riusare sia in UI sia nell'export.

### 3. Periodo di riferimento arbitrario (e allineamento delle finestre)

- Estendere `GET /portfolios/{id}/performance/summary` per accettare `start_date`/`end_date` oltre a `period` (il motore sottostante li supporta già: `get_performance_summary` delega a `calculate_twr`/`calculate_mwr` con date esplicite).
- Frontend: date picker per l'intervallo personalizzato accanto ai preset in `PerformanceKpiSummary.tsx:28-33` — richiede di aggiungere `@mantine/dates`, oggi assente dalle dipendenze.
- **Unificare la risoluzione del periodo** eliminando il doppio calcolo descritto sopra: gli hook in `hooks/queries.ts:234-342` accettano solo `startDate` benché il client API in `services/api/performance.ts` gestisca già `endDate`. Far derivare tutte le query dalla stessa coppia di date, così KPI e grafici coprono esattamente la stessa finestra.
- Mostrare l'intervallo effettivo ("Situazione portafoglio: 25/10/23 – 02/09/26") leggendo `start_date`/`end_date` dal summary, oggi ignorati dal frontend.

### 4. Resa

- **Card "Rendiconto"** in cima alla sezione Performance della dashboard (`components/dashboard/analysis/PerformanceMetrics.tsx`), con le cinque righe.
- **Export Markdown**: nuova sezione in `services/portfolio_markdown_export.py`, che già produce riepilogo, posizioni, performance, Doctor, Monte Carlo, target drift e PAC.

## Note

- Nell'export Markdown, `_PERF_PERIODS` (riga 12) omette `3y`, presente invece fra i preset del frontend: allineare.
- Il bottone "Esporta Dati in CSV" in `Settings.page.tsx:479` è un placeholder senza `onClick` e senza endpoint: valutare se rientra in questo lavoro o va tracciato a parte.

## Definition of Done

- Profilo e orizzonte si impostano, si salvano e sopravvivono al reload.
- La scheda mostra le cinque righe e lo scostamento dichiarato/effettivo.
- Un intervallo di date personalizzato produce TWR/MWR coerenti con i preset sullo stesso periodo.
- KPI e grafici, a parità di periodo selezionato, coprono la stessa identica finestra temporale.
- Test backend per i nuovi campi e per il summary con date arbitrarie; suite verde.
