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

## Decisioni approvate (giorno 3, 2026-11-02)

- **Shock per gold/commodity/crypto:** approvati i valori in `app/constants/stress_scenarios.py` (rimuovere la marcatura PROVVISORIO).
- **Reddito:** crescita 0% per i bond indicizzati all'inflazione; l'aliquota `fire_capital_gains_tax_rate` dell'utente continua a sovrascrivere il 26% predefinito, dichiarata in `tax_note`.
- **Ribilanciamento (TASK-39):** banda di tolleranza 0,5 pp; nessun importo minimo per ordine; la liquidità del portafoglio entra nel totale e nei pesi.
- **Stress storici (TASK-38):** copertura minima del 60% del peso con storico reale perché lo scenario sia "storico"; sotto soglia si usano i proxy per asset class, dichiarati.
- **Volatilità (TASK-40):** nessuna metrica canonica: entrambe esposte con nome, metodo, periodo e flag `is_floored`.

## Decisioni approvate (giorno 3, conferme)

- **Tabella proxy degli stress storici (TASK-38):** valori approvati, a condizione che l'utente veda nell'interfaccia che sono basati su indici in USD e non includono l'effetto cambio EUR/USD.
- **Banda di ribilanciamento (TASK-39):** 0,5 pp usata come soglia di attivazione (se uno strumento la supera, tutti tornano al target). Documentata nell'output del tool (`notes`), in `docs/mcp.md` e in `docs/mcp-guida-utente.md`.

## TASK-41 — Riconciliazione sui dati (2026-11-03)

Risultati delle query Q1–Q4 di `AUDIT_MCP_2026-11_QUERY_DATI.sql` forniti dal proprietario.

### Causa 1 (confermata): prezzo ×1000 e quantità ÷1000 nelle righe importate di Wealth

In Wealth (portafoglio 26), 17 acquisti di IBTM.L e SE15.L hanno prezzo moltiplicato per 1000 e quantità divisa per 1000 (es. id 5718: `0.005 × 157608` invece di `5 × 157.608`). Il controvalore è corretto, quindi il costo totale è giusto ma la quantità è troppo bassa.

- **Riguarda solo i prezzi con esattamente 3 decimali** (157.608, 105.568…): `_parse_italian_number` legge un punto seguito da 3 cifre come separatore delle migliaia. Il file XLSX conteneva celle numeriche, convertite con `str(105.123)`, e l'import ricalcola la quantità come `controvalore / prezzo`.
- **Il parser è già stato corretto** nel commit `b655330` (2026-10-23, `_xlsx_cell_to_str`); le righe di Wealth sono precedenti e restano errate nel database.
- **Effetto su IBTM.L in Wealth:** circa 43 quote mancanti (49,04 registrate contro circa 92 reali); costo medio implicito ~297,79 € invece di ~159 €.
- **Effetto su SE15.L in Wealth:** circa 29 quote mancanti (477,03 contro circa 506); costo medio ~112 € invece di ~105,6 €.
- **Il valore di mercato di Wealth è sottostimato** di circa 43 × 125 + 29 × 88 ≈ **7.900 €**: le quote mancanti non sono valorizzate.
- Parent non ha righe errate.

### Causa 2 (ipotesi forte, da confermare): valuta di quotazione dei listing di Londra

Tutti e 7 gli asset `.L` hanno `quote_currency = EUR` e nessuna borsa (Q1), mentre su Londra queste linee possono essere quotate in GBP o USD. I prezzi di carico di Parent sono coerenti con gli euro (SE15 105–110 €, IBTM 148–164 €), mentre i prezzi correnti scaricati da Yahoo (SE15.L 87,73; IBTM.L 123–125) sono compatibili con una quotazione in sterline letta come euro. Per confermare servono la Q2 estesa (ultimi prezzi di tutti i `.L`) e la valuta indicata dal broker.

### Altri controlli

- **Q4:** nessuna transazione in valuta estera senza tasso di cambio: il fallback a 1.0 non è mai scattato.

## TASK-42 — Riconciliazione sui dati (2026-11-03)

- **Q6:** in Wealth ci sono 7 gruppi di righe identiche, ciascuno ripetuto 4 volte, con id in 4 blocchi consecutivi nello stesso ordine (5806–5812, 5814–5820, 5821–5827, 5837–5843). Oltre a 6 dividendi (918,29 € per copia) è quadruplicato anche un acquisto di 31 EUN5.DE del 2026-08-04.
- **Q7:** il file `Lista Titoli (2).xlsx` è stato confermato 4 volte il 2026-10-23 (batch 31, 34, 35, 36; 19/19/18/18 righe; altri 2 batch annullati). La data coincide con il fix del parser `b655330`: probabilmente import di prova sui dati reali. Essendo cambiato il parser fra un import e l'altro, alcune copie potrebbero non essere identiche e quindi sfuggire alla Q6: serve l'elenco completo degli id 5790–5870.
- **Q8:** tutti i dividendi di Wealth sono in EUR (64 righe, 6.876,59 € lordi, ritenute a 0), quindi il problema delle valute miste in `get_dividend_summary` qui non ha effetti. Il totale include almeno 3 × 918,29 ≈ 2.755 € di duplicati.
- **Q5:** 8 asset con `quote_currency = EUR` su borse non in euro, incluso `IE00B441G979`, registrato con l'ISIN come simbolo.

Conclusione: i duplicati ci sono e la causa è il nuovo upload dello stesso file, senza deduplicazione fra batch. La correzione dei dati richiede un piano approvato, con anteprima delle righe coinvolte.

### Q9 — portata completa del bug ×1000 (2026-11-03)

39 acquisti in Wealth su 9 strumenti; nessuna riga in altri portafogli. Quote mancanti per strumento (quantità corretta − registrata): VWRA.L ~59,9; FRC3.DE ~116,9; IBTM.L ~43,0; IEVL.L ~30,0; SE15.L ~29,0; EUN5.DE ~20,0; DBXP.DE ~12,0; IHYG.L ~12,0; EQQQ.DE ~1,0. Il costo totale è corretto; quantità, costo medio e valore di mercato no.

Correzione proposta: `backlog/docs/AUDIT_MCP_2026-11_CORREZIONE_DATI.sql`, PARTE A (anteprima, copia di sicurezza, modifica con ROLLBACK di prova, annullamento). Da eseguire solo dopo l'approvazione del proprietario.

### Elenco degli id 5790–5870 (2026-11-03)

- In Wealth restano 4 copie dello stesso blocco di 7 righe: 5806–5812, 5814–5820, 5821–5827 e 5837–5843. Le altre righe dell'intervallo (5801 deposito, 5805 acquisto SE15, 5828–5836 vendite VWRA/EQQQ, 5844 prelievo) compaiono una volta sola. Le righe mancanti nell'intervallo (5790–5800, 5802–5804, 5813) non esistono più: probabilmente sono state cancellate a mano o non sono mai state confermate.
- Correzione proposta: PARTE B di `AUDIT_MCP_2026-11_CORREZIONE_DATI.sql` (elimina le 21 copie, tiene 5806–5812). Effetto: −2.754,87 € di dividendi (totale 4.121,72 €), −93 quote EUN5.DE.
- **Nuova anomalia (TASK-45):** l'import Fineco sembra contare due volte le commissioni. Le vendite di VWRA dello stesso ordine sono a 172,89, tranne quella con commissione (id 5828), che è a 153,89 = 172,89 − 19 ma registra anche `fees = 19`.

### Correzione dei dati eseguita (2026-11-03)

Il proprietario ha eseguito con COMMIT entrambe le parti di `AUDIT_MCP_2026-11_CORREZIONE_DATI.sql`:
- **Parte A:** 39 acquisti di Wealth corretti (prezzo ÷1000, quantità ×1000, controvalore invariato). Nessun prezzo anomalo rimasto.
- **Parte B:** 21 duplicati eliminati. Dividendi di Wealth: 46 righe, 4.121,72 € (prima 64 righe, 6.876,59 €). EUN5.DE: 242 quote.
- **Backup** (da eliminare quando non servono più): `backup_tx_fix_x1000_20261103`, `backup_tx_dup_import_20261103`.
