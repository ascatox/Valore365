# Audit MCP 2026-11 — Esito della verifica

> Verifica del 2026-11-02 sul codice del branch `main`, eseguita con script di riproduzione su dati sintetici e repository mock (nessun accesso a DB reali).
> Documento sorgente: `backlog/docs/AUDIT_MCP_2026-11-02.md`. Milestone: **m-1**.

## Riepilogo

| ID | Prio | Esito | Causa dimostrata | Task |
|---|---|---|---|---|
| V365-001 | P0 | CONFERMATO | Senza storico prezzi per la finestra dello scenario si usa `benchmark_drawdown * 0.8` (`_stress.py:95-101`), uguale per ogni portafoglio: -56.8×0.8 = -45.44 ecc. | TASK-38 |
| V365-002 | P0 | CONFERMATO | `_shock_asset_class` (`_stress.py:248`) riconosce solo `bond` o parole chiave nel nome, altrimenti `equity`; nessuna classe commodity; il fallback è lo shock equity (`_stress.py:204`). Il -5% equity in "Bond Selloff" è voluto dalla tabella scenari. | TASK-35 |
| V365-003 | P0 | CONFERMATO | I proventi delle vendite non finanziano gli acquisti; la vendita è calcolata come `drift% × valore della posizione` invece che del totale; `cash_used` conta due volte la liquidità. Il route `routes_rebalancing.py` ha già un algoritmo corretto. | TASK-39 |
| V365-004 | P1 | CONFERMATO (più grave) | `get_asset_by_symbol` restituisce solo `{id,symbol,name}` → `asset_type` assente → **tutto** finisce in equity, anche i `bond`. In più `FIXED_INCOME_TYPES={"bond"}` esclude gli ETF obbligazionari. | TASK-34, TASK-36 |
| V365-005 | P1 | CONFERMATO (più grave) | `get_portfolio_target_performance` restituisce rendimenti a 1 anno degli asset target, non variazioni giornaliere. Senza target/barre → `null` senza eccezione → nessun fallback. | TASK-33 |
| V365-006 | P1 | CONFERMATO | Le proiezioni vanno dall'anno 0 al 20; `[:10]` seguito dal filtro `year>0` → anni 1..9. Valori in indice base 100, non in euro. | TASK-33 |
| V365-007 | P1 | CONFERMATO (+ bug di unità) | Il TER ponderato è normalizzato sul peso coperto, mentre il costo annuo è una somma parziale; nessun campo di copertura. **Bug extra:** `expense_ratio` non è normalizzato (`copilot_tools.py:1045`) → TER 100× più piccolo. `infer_ter` restituisce 0 per stock/bond, che vengono contati come coperti. | TASK-34 |
| V365-008 | P1 | DA DEFINIRE | Rischi nel codice confermati: `quote_currency` = valuta base del portafoglio alla creazione dell'asset (ignora la valuta del listing); FX mancante → fallback silenzioso a 1.0; nessuna normalizzazione GBp. Va riconciliato sui dati con la query in sola lettura (TASK-41). | TASK-41 |
| V365-009 | P1 | CONFERMATO (rischio) | Nessun id esterno, hash o vincolo di unicità sulle transazioni; `commit_batch` non è atomico (doppio commit possibile); un nuovo upload dello stesso file reinserisce. Che le 4 righe siano duplicate va verificato sui dati. | TASK-42 |
| V365-010 | P2 | CONFERMATO | Il 16.0 è il pavimento della volatilità equity a lungo termine (`_holdings.py:174,246`); la volatilità dell'health è una media ponderata senza correlazioni. `category_scores` non è esposto dal tool. | TASK-40 |
| V365-011 | P2 | CONFERMATO | L'MCP accetta un solo `portfolio_id`; esistono già `resolve_portfolio_scope` e i metodi `*_multi`. | TASK-43 |
| V365-012 | P2 | CONFERMATO | `QUOTE_TYPE_MAP`: tipo sconosciuto o EQUITY → `stock`; l'import CSV forza `stock`; lo schema non ha `etc`/`commodity`. A valle: TER 0, peso equity, rischio "singola azione", regione Europa. | TASK-35 |
| V365-013 | P2 | CONFERMATO (+ bug) | Gli errori sono solo testo, senza codice né `retry_after`. **Bug:** la quota dei tool pesanti viene consumata prima del controllo di concorrenza, quindi anche le chiamate rifiutate come "busy" la esauriscono. | TASK-33 |

Altre anomalie emerse durante la verifica:
- `get_dividend_summary` somma importi in valute diverse senza conversione FX (`copilot_tools.py:964`) → TASK-42.
- `get_asset_by_symbol` fa un match debole sul ticker base (`XAD1.DE` può risolvere su un altro listing) → TASK-36.
- `Position.day_change_pct` vale `0.0` di default, quindi il filtro `is not None` non ha effetto → TASK-33.
- Il fallback del Monte Carlo/ribilanciamento non ha test di logica, solo test di contratto MCP.

## Decisioni di metodologia richieste (bloccanti per i task indicati)

Raccolte in **TASK-37**. Le opzioni consigliate sono marcate con ★.

1. **Ribilanciamento (TASK-39)**
   - Modalità predefinita: ★ (b) vendite+acquisti autofinanziati; (a) solo nuova liquidità; (c) solo vendite.
   - `available_cash`: ★ liquidità aggiuntiva rispetto a quella del portafoglio; oppure sostitutiva.
   - Liquidità del portafoglio inclusa nel totale e nei pesi: sì/no.
   - Banda di tolleranza 0.5 pp fissa vs relativa; importo minimo dell'ordine.
2. **Stress storici senza dati (TASK-38)**: (a) scenario "dati insufficienti" con `coverage_pct`; ★ (b) proxy di drawdown per asset class e scenario (tabella da approvare); (c) backfill dello storico / mappatura degli ETF su indici proxy. Copertura minima per considerare valido uno scenario.
3. **Shock per asset class (TASK-35)**: entità degli shock su commodity/oro nel crash tech e sull'equity nel selloff obbligazionario; il crash tech USA colpisce l'equity non USA per intero? Asset non classificabili: ★ classe `unknown` dichiarata, oppure equity prudenziale.
4. **Tipizzazione asset (TASK-35)**: (a) nuovo tipo `etc`/`commodity` (migrazione); ★ (b) mantenere `etf` e ricavare l'asset class in modo separato; (c) colonna `asset_class` dedicata.
5. **Reddito (TASK-36)**: fiscalità ★ 26% + `tax_note`, oppure 12.5% approssimato sugli ETF di titoli di stato; crescita dei bond indicizzati all'inflazione: 0% o ipotesi di inflazione.
6. **TER mancanti (TASK-34)**: ★ TER sul peso coperto + copertura esplicita; null sotto una soglia (es. 80%)? I TER dedotti/da pattern contano come coperti?
7. **Volatilità/score (TASK-40)**: quale volatilità è quella canonica; pavimento nello stress sì/no; 100/100 raggiungibile?
8. **Dati (TASK-41, TASK-42)**: backfill di `quote_currency` sugli asset esistenti (cambia le valorizzazioni storiche); costo medio vs FIFO; chiave di deduplicazione (avviso vs blocco) e bonifica dei duplicati esistenti.
9. **Aggregato MCP (TASK-43)**: tool dedicati vs parametro `portfolio_ids`; costo sul rate limit.

## Script di riproduzione

Gli script della verifica erano nello scratchpad della sessione (temporaneo, non versionato). La parte TEST di ogni task li sostituisce con test pytest in `src/backend/tests/unit/`.

## Piano su più giornate

Ogni task segue il ciclo `AUDIT -> TEST (che fallisce) -> FIX -> VERIFY`, lavorato da un sub-agente e verificato prima della chiusura. Branch e PR separate per ambito.

| Giornata | Task | Note |
|---|---|---|
| 1 | TASK-37 (decisioni), TASK-33, TASK-34 | Le decisioni si avviano subito. TASK-33 e TASK-34 non hanno decisioni bloccanti (per TASK-34 si usa l'opzione ★, rivedibile). |
| 2 | TASK-35, TASK-36 | Il classificatore unico sblocca reddito, stress e health. |
| 3 | TASK-38, TASK-39, TASK-40 | Richiedono le decisioni di TASK-37. |
| 4 | TASK-41, TASK-42 | Prima l'indagine in sola lettura sui dati reali (a cura del proprietario), poi le correzioni. Nessuna modifica ai dati esistenti senza un piano approvato. |
| 5 | TASK-43, TASK-44 | Aggregato MCP, controlli della sezione C, methodology.md e regression-results.md. |

Per riprendere: `backlog task list -m m-1 --plain`, poi spostare il task in "In Progress" prima di iniziare.

## Decisioni approvate (2026-11-02)

Approvate dal proprietario le opzioni ★:
- **Ribilanciamento:** modalità predefinita vendite+acquisti autofinanziati; `available_cash` è liquidità aggiuntiva a quella del portafoglio.
- **Stress storici senza dati:** proxy di drawdown per asset class e scenario, con `coverage_pct` e metodo esplicito.
- **Asset non classificabili:** classe `unknown` dichiarata (niente default silenzioso in equity).
- **Tipizzazione ETC:** si mantiene `asset_type=etf`; l'asset class (gold/commodity) è ricavata separatamente, senza migrazione dello schema.
- **Fiscalità del reddito:** 26% uniforme, dichiarato nell'output con `tax_note`.
- **TER mancanti:** TER ponderato sul peso coperto, con copertura esplicita (`ter_coverage_pct`, `missing_ter_symbols`).

Ancora aperte (da decidere prima del task indicato): banda di tolleranza, ordine minimo e liquidità nei pesi (TASK-39); tabella dei proxy e copertura minima (TASK-38); entità degli shock per classe (TASK-35/38); crescita dei bond indicizzati all'inflazione (TASK-36); soglia di copertura TER e TER dedotti (TASK-34, per ora: i TER dedotti sono contati come coperti ma marcati `ter_source=inferred`); volatilità canonica (TASK-40); backfill di `quote_currency` e FIFO (TASK-41); chiave di deduplicazione (TASK-42); forma dell'aggregato MCP (TASK-43).
