# Analisi Competitiva: net-worth-tracker vs Valore365

**Data**: 2026-04-04
**Repo analizzato**: [GiuseppeDM98/net-worth-tracker](https://github.com/GiuseppeDM98/net-worth-tracker)

---

## Panoramica

Il concorrente e un'app Next.js + Firebase per il tracking del patrimonio netto personale,
focalizzata sul mercato italiano (UI in italiano, tassazione IT, integrazione Borsa Italiana).
E molto verticale su dividendi, storico patrimonio, e pianificazione FIRE.

Valore365 e un'app React + Python/FastAPI + Supabase/PostgreSQL, con focus su
portfolio analysis, AI copilot, e portfolio doctor diagnostics.

---

## Feature che NON abbiamo (gap da colmare)

### 1. Gestione Dividendi

| Feature concorrente                                                 | Stato Valore365                                           |
| ---------------------------------------------------------------------| -----------------------------------------------------------|
| Registrazione dividendi multi-valuta con conversione EUR            | **Assente** (abbiamo solo transazioni dividend come side) |
| Tipi: ordinario, straordinario, interim, finale                     | **Assente**                                               |
| Scraping Borsa Italiana per ISIN (storico dividendi)                | **Assente**                                               |
| Generazione automatica cedole obbligazionarie (step-up, BTP Valore) | **Assente**                                               |
| Calcolo ritenuta 26% automatico                                     | **Assente**                                               |
| Calendario dividendi con visualizzazione giornaliera                | **Assente**                                               |
| Dividendi futuri previsti                                           | **Assente**                                               |
| Yield on Cost, Current Yield                                        | **Assente**                                               |

**Impatto**: Alto per utenti italiani con portafogli obbligazionari/ETF a distribuzione.

### 2. Snapshot Storici / History

| Feature concorrente                                   | Stato Valore365 |
| -------------------------------------------------------| -----------------|
| Snapshot mensili automatici (cron)                    | **Assente**     |
| Snapshot manuali con conferma sovrascrittura          | **Assente**     |
| Dettaglio per asset class e per singolo asset         | **Assente**     |
| Note sugli snapshot (eventi finanziari significativi) | **Assente**     |
| Ricerca snapshot                                      | **Assente**     |
| Milestone di raddoppio (geometrico e soglia)          | **Assente**     |
| Variazione anno su anno                               | **Assente**     |
| Tabella storico prezzi con variazioni mensili, YTD    | **Assente**     |

**Impatto**: Alto. Senza snapshot storici non si puo tracciare l'evoluzione del patrimonio.

### 3. Hall of Fame / Record personali

| Feature concorrente                                    | Stato Valore365 |
| --------------------------------------------------------| -----------------|
| Classifica mesi/anni migliori e peggiori (8 categorie) | **Assente**     |
| Note personali per periodo                             | **Assente**     |

**Impatto**: Medio-basso. Gamification / engagement.

### 4. Obbligazioni con modello cedolare completo

| Feature concorrente                                  | Stato Valore365                                                      |
| ------------------------------------------------------| ----------------------------------------------------------------------|
| Cedola con tasso, frequenza, date emissione/scadenza | **Assente** (abbiamo asset_type "bond" ma senza modellazione cedole) |
| Step-up rate schedules (BTP Valore)                  | **Assente**                                                          |
| Valore nominale e premio finale                      | **Assente**                                                          |

**Impatto**: Alto per il mercato italiano.

### 5. Compositi / Fondi pensione

| Feature concorrente | Stato Valore365 |
|---|---|
| Asset compositi con allocazione mista (es. 60% equity / 40% bond) | **Assente** |

**Impatto**: Medio. Utile per fondi pensione e prodotti multi-asset.

### 6. PDF Export

| Feature concorrente | Stato Valore365 |
|---|---|
| Report PDF con 7 sezioni selezionabili | **Assente** |
| Filtro per periodo (totale, annuale, mensile) | **Assente** |
| Grafici catturati via html2canvas | **Assente** |

**Impatto**: Medio. Utile per consulenti e documentazione personale.

### 7. Goal-Based Investing

| Feature concorrente | Stato Valore365 |
|---|---|
| Creazione obiettivi finanziari (nome, priorita, target, data) | **Assente** |
| Assegnazione asset a obiettivi con % | **Assente** |
| Progress tracking per obiettivo | **Assente** |
| Allocazione target derivata dagli obiettivi | **Assente** |

**Impatto**: Medio-alto. Differenziante per la pianificazione finanziaria.

### 8. Tassazione e Imposta di Bollo

| Feature concorrente | Stato Valore365 |
|---|---|
| Calcolo imposta di bollo con soglia 5.000 EUR | **Assente** |
| Tax rate personalizzabile per asset | Parziale (abbiamo capital_gains_tax_rate nelle settings FIRE) |

**Impatto**: Medio per il mercato italiano.

### 9. Heatmap rendimenti mensili

| Feature concorrente | Stato Valore365 |
|---|---|
| Griglia anno x mese con rendimenti colorati | **Assente** |
| Underwater drawdown chart | **Assente** |
| Rolling windows (12m, 36m) per CAGR, volatilita, Sharpe | **Assente** |

**Impatto**: Medio. Miglioramento visuale della sezione performance.

---

## Feature dove siamo GIA IN PARI o AVANTI

| Area | Valore365 | Concorrente |
|---|---|---|
| **AI Copilot interattivo** | Chat contestuale per pagina con streaming, multi-provider | Analisi AI una-tantum (solo performance) |
| **Portfolio Doctor** | Health score, X-Ray, Stress Test, Monte Carlo, Education layer | Non presente |
| **Instant Portfolio Analyzer** | Analisi pubblica senza login | Non presente |
| **Creator / Wizard** | Creazione guidata portfolio con quiz profilo, model library | Non presente |
| **Multi-portfolio** | Si, con portfolio switcher e clone | Non presente (single-portfolio) |
| **Asset Discovery** | Ricerca asset con auto-complete da provider | Manuale |
| **CSV Import** | Import transazioni e target allocation via CSV | Solo scraping Borsa Italiana |
| **Target Allocation + Rebalancing** | Target allocation con preview rebalancing | Simile (3 livelli) |
| **PAC (Piano di Accumulo)** | Regole PAC configurabili | Non presente |
| **Market data tab** | Ticker di mercato, news in tempo reale | Non presente |
| **Performance metrics** | CAGR, TWR, Sharpe, drawdown, best/worst performers | Simile (piu metriche rolling) |
| **Monte Carlo** | Si, nella pagina FIRE | Simile |
| **FIRE Calculator** | Proiezione deterministrica + Monte Carlo + decumulation | Simile (3 scenari + Monte Carlo + Goal-Based) |
| **Tech stack backend** | Python/FastAPI + PostgreSQL (scalabile) | Firebase (serverless) |
| **PWA** | Si | Non specificato |
| **Privacy mode** | Mascheramento valori | Non presente |
| **Admin panel** | Dashboard usage, gestione utenti | Non presente |
| **Auth** | Clerk (social login, MFA) | Firebase Auth (email/password) |
| **Dark mode** | Si | Si |
| **Mobile responsive** | Si, con bottom nav, carousel, pull-to-refresh | Si, con bottom nav |

---

## Piano di Implementazione (prioritizzato)

### Fase 1 - Fondamenta storiche (Alta priorita)

**Snapshot storici del patrimonio**
- Schema DB: tabella `snapshots` con data, net_worth totale, breakdown per asset class e per asset
- Cron job (scheduler gia presente) per snapshot mensile automatico
- API CRUD snapshot + note
- Frontend: pagina History con grafico evoluzione patrimonio, tabella snapshot, ricerca
- Milestone di raddoppio
- **Effort stimato**: 2-3 settimane

### Fase 2 - Dividendi e cedole (Alta priorita)

**Gestione dividendi strutturata**
- Schema DB: tabella `dividends` con tipo, valuta, conversione EUR, ritenuta
- Modellazione cedole obbligazionarie: frequenza, step-up, valore nominale, premio finale
- Generazione automatica cedole future
- Calendario dividendi
- Statistiche per asset e per tipo
- Scraping Borsa Italiana per ISIN (opzionale, via justetf_client gia presente)
- **Effort stimato**: 2-3 settimane

### Fase 3 - Goal-Based Investing (Media priorita)

**Obiettivi finanziari**
- Schema DB: tabelle `goals`, `goal_asset_allocations`
- CRUD obiettivi con priorita, target amount, data target
- Assegnazione asset a obiettivi con validazione (max 100%)
- Progress tracking e allocazione derivata
- Integrazione con pagina FIRE esistente
- **Effort stimato**: 2 settimane

### Fase 4 - Visualizzazioni avanzate (Media priorita)

**Miglioramenti analytics**
- Heatmap rendimenti mensili (griglia anno x mese)
- Underwater drawdown chart
- Rolling windows (12m, 36m) per metriche chiave
- Hall of Fame (best/worst mesi e anni)
- **Effort stimato**: 1-2 settimane

### Fase 5 - PDF Export (Bassa priorita)

**Report esportabile**
- Integrare `@react-pdf/renderer` o `html-to-image` (gia presente nel progetto)
- Sezioni selezionabili: assets, allocation, history, performance, FIRE
- Filtro periodo
- **Effort stimato**: 1-2 settimane

### Fase 6 - Tassazione italiana (Bassa priorita)

**Calcoli fiscali**
- Imposta di bollo con soglia 5.000 EUR per conti correnti
- Tax rate per asset
- Capital gain report annuale
- **Effort stimato**: 1 settimana

---

## Riepilogo

| Metrica | Valore365 | Concorrente |
|---|---|---|
| Feature totali uniche | ~12 | ~10 |
| Gap critici da colmare | 2 (snapshot, dividendi) | - |
| Vantaggio competitivo | AI copilot, Doctor, Instant Analyzer, multi-portfolio | Dividendi, snapshot storici, PDF, goal-based |
| Effort totale stimato | ~8-12 settimane | - |

**Nota**: Il modulo cashflow/spese e il tracking immobiliare del concorrente sono fuori scope
per Valore365, focalizzato esclusivamente sulla gestione di portafoglio finanziario.

**Conclusione**: Valore365 ha un vantaggio significativo sull'intelligenza artificiale e la diagnostica
del portfolio. I gap piu critici da colmare sono gli snapshot storici e la gestione dividendi/cedole,
fondamentali per un sistema di portfolio management completo.
