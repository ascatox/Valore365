# Portfolio Tracker MVP - Specifiche

## Obiettivo MVP

Realizzare un portfolio tracker semplice che permetta all'utente di:

- inserire transazioni manualmente
- visualizzare le posizioni correnti
- vedere il valore totale del portafoglio e il profit/loss
- consultare lo storico movimenti
- osservare l'allocazione del portafoglio

Focus MVP: dare valore subito con una prima versione usabile, evitando integrazioni complesse e funzionalita' avanzate.

## Ambito MVP (In Scope)

### 1. Gestione portafoglio singolo

- Un solo portafoglio per utente (o una sola istanza, se senza autenticazione)
- Valuta base configurabile (default consigliato: `EUR`)

### 2. Inserimento transazioni manuale

Supportare almeno i seguenti tipi di transazione:

- `BUY`
- `SELL`

Campi minimi per transazione:

- Data
- Ticker / simbolo strumento
- Quantita'
- Prezzo unitario
- Commissioni (opzionale, default `0`)

Funzionalita':

- Creazione transazione
- Modifica transazione
- Eliminazione transazione
- Validazioni base (quantita' > 0, prezzo >= 0, data valida, ticker obbligatorio)

### 3. Lista posizioni correnti

Per ogni posizione mostrare:

- Ticker
- Quantita' attuale
- Prezzo medio di carico
- Prezzo corrente
- Valore posizione corrente
- P/L assoluto
- P/L percentuale

Note:

- Le posizioni vengono calcolate a partire dallo storico transazioni
- Se una posizione va a zero, puo' essere nascosta dalla vista principale (opzionale)

### 4. Dashboard base

KPI minimi:

- Valore totale portafoglio
- P/L totale (assoluto e percentuale)
- Numero posizioni aperte
- Cash disponibile

### 5. Allocazione portafoglio

Visualizzazione semplice dell'allocazione:

- per asset/ticker (minimo richiesto)
- oppure per categoria semplice (`azioni`, `ETF`, `cash`) se disponibile

Output suggerito:

- grafico a torta / donut
- tabella con percentuale per voce

### 6. Storico transazioni

Tabella con:

- Data
- Tipo (`BUY` / `SELL`)
- Ticker
- Quantita'
- Prezzo
- Commissioni
- Totale operazione

Funzionalita':

- ordinamento per data (default: piu' recenti prima)
- modifica/eliminazione riga

### 7. Aggiornamento prezzi (versione semplice)

Per l'MVP, scegliere una delle due opzioni:

- Modalita' manuale: inserimento prezzo corrente per ciascun ticker
- Modalita' semi-automatica: integrazione limitata a una fonte prezzi per un set ristretto di ticker

Scelta consigliata per MVP iniziale:

- **manuale**, per ridurre complessita' e dipendenze esterne

### 8. Persistenza dati

Salvare in database almeno:

- portafoglio
- transazioni
- prezzi correnti (se manuali)

Autenticazione:

- opzionale per MVP interno / demo
- necessaria se il prodotto e' multiutente fin dalla prima release

## Fuori Scope MVP (Out of Scope)

Le seguenti funzionalita' sono escluse dalla prima versione:

- Sync con broker/exchange via API
- Fiscalita' (plus/minusvalenze, report fiscali)
- Dividendi / cedole / interessi
- Multi-portafoglio
- Multi-valuta avanzata
- Benchmark e metriche avanzate (`TWR`, `Sharpe`, `VaR`, ecc.)
- Alert e automazioni
- Mobile app nativa

## Priorita' di sviluppo (ordine consigliato)

1. Transazioni manuali + calcolo posizioni
2. Dashboard base + P/L totale
3. Storico transazioni (CRUD)
4. Allocazione grafica
5. Aggiornamento prezzi (manuale, poi eventuale automatico)

## Requisiti funzionali minimi (sintesi)

- L'utente puo' inserire acquisti e vendite
- Il sistema ricalcola posizioni e prezzo medio
- Il sistema mostra valore portafoglio e P/L
- L'utente puo' vedere e correggere lo storico transazioni
- Il sistema mostra una vista di allocazione

## Criteri di accettazione MVP

- Inserendo una sequenza di `BUY` e `SELL`, la quantita' residua per ticker e' corretta
- Il prezzo medio di carico viene calcolato correttamente sulle posizioni aperte
- Il valore totale del portafoglio coincide con la somma di posizioni + cash
- Le modifiche/eliminazioni di transazioni aggiornano correttamente dashboard e posizioni
- L'interfaccia mostra almeno una vista dashboard, una vista posizioni e una vista storico transazioni

## Note implementative (pragmatiche)

- Iniziare con prezzi manuali riduce il rischio di blocchi su API esterne
- Calcolare sempre le posizioni partendo dalle transazioni (single source of truth)
- Separare chiaramente:
  - dati transazionali
  - calcoli di portfolio (P/L, prezzo medio, allocazione)
  - dati di mercato (prezzi correnti)

