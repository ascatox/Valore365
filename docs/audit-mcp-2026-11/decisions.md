# Audit MCP 2026-11 — Decisioni di metodologia finanziaria

Le decisioni sono raccolte in TASK-37 e nel documento di verifica
(`backlog/docs/AUDIT_MCP_2026-11_VERIFICA.md`). "Proprietario" = il titolare del repository e dei
portafogli; le opzioni sono state proposte dall'assistente e approvate dal proprietario.

## Approvate

| # | Decisione | Approvata da / quando | Task |
|---|---|---|---|
| 1 | Ribilanciamento: modalità predefinita vendite+acquisti autofinanziati; `available_cash` è liquidità aggiuntiva a quella del portafoglio | Proprietario, 2026-11-02 | TASK-39 |
| 2 | Stress storici senza dati: proxy di drawdown per asset class, con `coverage_pct` e metodo esplicito | Proprietario, 2026-11-02 | TASK-38 |
| 3 | Asset non classificabili: classe `unknown` dichiarata, mai equity per default | Proprietario, 2026-11-02 | TASK-35 |
| 4 | ETC: resta `asset_type=etf`, asset class (gold/commodity) ricavata separatamente, nessuna migrazione | Proprietario, 2026-11-02 | TASK-35 |
| 5 | Fiscalità del reddito: 26% uniforme dichiarato in `tax_note` | Proprietario, 2026-11-02 | TASK-36 |
| 6 | TER mancanti: TER ponderato sul peso coperto, con `ter_coverage_pct` e `missing_ter_symbols`; i TER dedotti contano come coperti, marcati `ter_source=inferred` | Proprietario, 2026-11-02 (il trattamento dei dedotti è provvisorio) | TASK-34 |
| 7 | Shock gold/commodity/crypto: valori di `stress_scenarios.py` (rimossa la marcatura PROVVISORIO) | Proprietario, 2026-11-02 (giorno 3) | TASK-35/38 |
| 8 | Reddito: crescita 0% per i bond indicizzati all'inflazione; `fire_capital_gains_tax_rate` dell'utente sovrascrive il 26%, dichiarato in `tax_note` | Proprietario, 2026-11-02 (giorno 3) | TASK-36 |
| 9 | Ribilanciamento: banda 0,5 pp, nessun ordine minimo, liquidità del portafoglio nel totale e nei pesi | Proprietario, 2026-11-02 (giorno 3) | TASK-39 |
| 10 | Banda di 0,5 pp usata come soglia di attivazione (se uno strumento la supera, tutti tornano al target), documentata in `notes`, `docs/mcp.md`, `docs/mcp-guida-utente.md` | Proprietario, 2026-11-02 (conferme giorno 3) | TASK-39 |
| 11 | Stress storici: copertura minima 60% del peso con storico reale; sotto soglia proxy dichiarati | Proprietario, 2026-11-02 (giorno 3) | TASK-38 |
| 12 | Tabella dei proxy storici approvata, a condizione che l'utente veda che sono indici in USD senza effetto cambio EUR/USD | Proprietario, 2026-11-02 (conferme giorno 3) | TASK-38 |
| 13 | Volatilità: nessuna metrica canonica, entrambe esposte con nome, metodo, periodo, `is_floored` | Proprietario, 2026-11-02 (giorno 3) | TASK-40 |
| 14 | Import: nessuna migrazione dello schema; commit atomico, batch non confermabile due volte; righe già presenti segnalate ed escluse per default | Proposta dall'assistente, approvata dal proprietario ("procedi"), 2026-11-03 | TASK-42 |
| 15 | Aggregato MCP: tool dedicati `get_aggregate_*` con `portfolio_ids` (2-20, stessa valuta); una chiamata = una unità di rate limit, le pesanti sulla quota pesante | Proposta dall'assistente, avviata dal proprietario ("start"), 2026-11-03 | TASK-43 |

## Prese in TASK-44 senza nuova approvazione (solo trasparenza, nessuna regola finanziaria nuova)

- `get_dividend_summary` con dividendi in più valute: totali per valuta e totali complessivi `null`
  (nessuna conversione FX inventata); oggi senza effetto (tutti i dividendi sono in EUR).
- Un quote type Yahoo `BOND` non cambia il tipo di un asset già `etf`/`fund` (coerente con la
  decisione 4).

## Ancora aperte

| Decisione | Opzioni | Blocca |
|---|---|---|
| Backfill di `quote_currency` sui listing `.L` (cambia le valorizzazioni storiche) e normalizzazione GBp | backfill con piano approvato / solo nuovi asset | TASK-41 |
| Costo medio ponderato vs FIFO | mantenere il costo medio / FIFO per lotti | TASK-41 |
| Semantica di prezzo e commissioni nell'export Fineco | prezzo netto/lordo della commissione; da confermare su un estratto conto reale | TASK-45 |
| Correzione dei dati di Wealth: PARTE A (39 acquisti ×1000) e PARTE B (21 duplicati) di `backlog/docs/AUDIT_MCP_2026-11_CORREZIONE_DATI.sql` | esecuzione da parte del proprietario dopo anteprima e copia di sicurezza | TASK-41, TASK-42 |
| Modello della liquidità nel TWR/MWR (issue C1-TWR-MIXED) | (a) gli acquisti scalano la liquidità quando il portafoglio usa depositi; (b) acquisti/vendite sempre flussi esterni; (c) scelta per portafoglio dichiarata | nuovo task |
| Dividendi con ritenuta: liquidità al lordo o al netto di `taxes` | lordo (attuale) / netto | nuovo task |
| Soglia minima di copertura TER sotto cui restituire `null` | es. 80% / nessuna soglia (attuale) | TASK-34 (follow-up) |
| Tolleranza contabile sulle quantità frazionarie (residui) | soglia esplicita / nessuna (attuale) | nuovo task |
