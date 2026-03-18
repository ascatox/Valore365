Piano: Backfill automatico + Validazione dati per grafici

     Contesto

     I grafici del dashboard mostrano risultati assurdi perché:
     1. Nessun backfill automatico: quando si aggiunge un titolo (transazione o
     target allocation), non viene scaricato lo storico prezzi. Senza dati in
     price_bars_1d, il grafico mostra valori a 0 o salti improvvisi.
     2. Nessun controllo di copertura: il backend genera grafici anche con 0
     barre di prezzo, producendo serie temporali piene di buchi.

     ---
     Feature 1: Backfill automatico su creazione transazione / target allocation

     Step 1 — Nuovo metodo backfill_single_asset in historical_service.py

     Aggiungere un metodo che fa il backfill di un singolo asset (365 giorni).
     Riusa la logica esistente del loop in backfill_daily (righe 38-74 per prezzi,
     76-112 per FX):

     - Chiama repo.get_asset_pricing_symbol(asset_id, provider) (repository.py:839)
     - Chiama client.get_daily_bars() per lo storico OHLC
     - Chiama repo.batch_upsert_price_bars_1d() per salvare
     - Controlla se quote_currency != base_currency → se sì, chiama
     client.get_daily_fx_rates() + repo.batch_upsert_fx_rates_1d()
     - Tutto in try/except: errori loggati ma mai propagati (è un task background)

     Step 2 — Trigger background in create_transaction (main.py:328-333)

     Dopo repo.create_transaction(payload), lanciare un
     threading.Thread(daemon=True) che chiama
     historical_service.backfill_single_asset(asset_id=payload.asset_id, portfolio_id=payload.portfolio_id).

     La risposta resta TransactionRead (nessun cambio di API).

     Step 3 — Trigger background in upsert_target_allocation (main.py:513-524)

     Stessa logica: dopo il return del repo.upsert_portfolio_target_allocation(),
     lanciare il thread con backfill_single_asset(asset_id=payload.asset_id, portfolio_id=portfolio_id).

     Step 4 — Feedback nel frontend (Portfolio.page.tsx)

     Cambiare i messaggi di successo:
     - Riga 681: 'Transazione salvata' → 'Transazione salvata. Caricamento storico  prezzi in corso...'
     - Riga 552: 'Peso salvato correttamente' → 'Peso salvato. Caricamento storico  prezzi in corso...'

     ---
     Feature 2: Validazione copertura dati + warning nel dashboard

     Step 5 — Nuovo metodo get_price_coverage in repository.py

     Query leggera con COUNT + GROUP BY su price_bars_1d LEFT JOIN
     portfolio_target_allocations:
     - Per ogni asset nel target: bar_count, first_bar, last_bar,
     coverage_pct (bar_count/days*100)
     - Usa l'indice esistente idx_price_bars_1d_asset_date_desc

     Step 6 — Nuovi modelli Pydantic in models.py

     class AssetCoverageItem(BaseModel):
         asset_id: int
         symbol: str
         name: str
         bar_count: int
         first_bar: date | None
         last_bar: date | None
         expected_bars: int
         coverage_pct: float

     class DataCoverageResponse(BaseModel):
         portfolio_id: int
         days: int
         sufficient: bool
         threshold_pct: float
         assets: list[AssetCoverageItem]

     Step 7 — Nuovo endpoint GET /portfolios/{id}/data-coverage in main.py

     Parametri query: days (default 365), threshold_pct (default 80).
     sufficient = True se tutti gli asset hanno coverage_pct >= threshold_pct.

     Step 8 — Funzione API nel frontend (api.ts)

     Aggiungere DataCoverageResponse interface + getPortfolioDataCoverage().

     Step 9 — Integrare in useDashboardData.ts

     - Nuovo state: dataCoverage
     - Aggiungere getPortfolioDataCoverage(portfolioId) al Promise.all in
     loadDashboardData (riga 108)
     - Esporre dataCoverage nel return (riga 375+)

     Step 10 — Aggiornare tipo DashboardData in types.ts

     Aggiungere dataCoverage: DataCoverageResponse | null; all'interfaccia (dopo
     riga 100).

     Step 11 — Warning banner in PanoramicaTab.tsx

     Sopra il grafico performance, aggiungere un <Alert color="yellow">
     condizionale quando dataCoverage.sufficient === false. Mostra la lista degli
     asset con copertura insufficiente (es. "AAPL (12%), MSFT (0%)") e invita a
     premere il pulsante aggiornamento.

     ---
     File da modificare

     ┌────────────────────────────────────────────────────┬───────────────────────────────────────────┐
     │                        File                        │                 Modifica                  │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ src/backend/app/historical_service.py              │ + backfill_single_asset()                 │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ src/backend/app/main.py                            │ + threading in create_transaction e       │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ upsert_target_allocation, + endpoint data-coverage │                                           │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ src/backend/app/repository.py                      │ + get_price_coverage()                    │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ src/backend/app/models.py                          │ + AssetCoverageItem, DataCoverageResponse │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ src/frontend/.../services/api.ts                   │ + interface + fetch function              │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ src/frontend/.../hooks/useDashboardData.ts         │ + state dataCoverage, +                   │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ chiamata in loadDashboardData                      │                                           │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ src/frontend/.../types.ts                          │ + campo dataCoverage in DashboardData     │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ src/frontend/.../tabs/PanoramicaTab.tsx            │ + Alert warning                           │
     ├────────────────────────────────────────────────────┼───────────────────────────────────────────┤
     │ src/frontend/.../pages/Portfolio.page.tsx          │ testi successo aggiornati                 │
     └────────────────────────────────────────────────────┴───────────────────────────────────────────┘

     Verifica

     1. Creare una transazione per un asset nuovo → verificare nei log che il thread
     di backfill parte e salva le barre
     2. Aggiungere un asset al target allocation → stessa verifica
     3. Chiamare GET /portfolios/{id}/data-coverage → verificare che restituisce i
     conteggi corretti
     4. Aprire il dashboard con dati insufficienti → verificare che l'Alert giallo
     compare
     5. Premere "Aggiorna" → verificare che dopo il backfill l'Alert scompare