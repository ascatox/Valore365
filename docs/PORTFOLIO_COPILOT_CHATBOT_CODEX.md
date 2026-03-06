# Portfolio Copilot Chatbot CODEX

## Obiettivo

Introdurre un chatbot basato su ChatGPT con comportamento agentic leggero, pensato per fornire supporto finanziario semplice e contestuale sui dati di ciascun portafoglio.

L'obiettivo non e' dare consulenza finanziaria avanzata, ma aiutare l'utente a capire:

- come sta andando il portafoglio
- perche' oggi il valore e' salito o sceso
- quali posizioni pesano di piu'
- quanto cash e' disponibile
- quanto il portafoglio e' distante dal target
- come leggere KPI, grafici e trend

## Principio chiave

Non costruire un chatbot generico che prova a rispondere a tutto.

Costruire invece un `Portfolio Copilot` con accesso controllato ai dati del prodotto.

## Architettura consigliata

### Frontend

- pulsante o entry point `Chiedi al Copilot`
- drawer laterale su desktop
- bottom sheet su mobile
- quick prompts iniziali
- cronologia sessione limitata

### Backend

Nuovo endpoint dedicato:

- `POST /api/copilot/chat`

Il backend:

1. riceve `portfolio_id` e `message`
2. recupera i dati necessari dal sistema
3. costruisce un contesto strutturato
4. invia il contesto al modello
5. restituisce una risposta sintetica e leggibile

## Pattern corretto: snapshot strutturato

Il modello non dovrebbe leggere direttamente il DB o ricevere dump troppo grandi.

Il backend deve costruire uno snapshot pulito e piccolo.

Esempio:

```json
{
  "portfolio": {
    "id": 7,
    "name": "ETF Core",
    "base_currency": "EUR",
    "market_value": 104230.12,
    "cash_balance": 5120.44,
    "unrealized_pl": 8420.11,
    "unrealized_pl_pct": 8.78,
    "day_change": -312.4,
    "day_change_pct": -0.29
  },
  "top_positions": [
    { "symbol": "VWCE", "weight": 34.2, "market_value": 35600 },
    { "symbol": "AGGH", "weight": 18.4, "market_value": 19180 }
  ],
  "target_drift": [
    {
      "symbol": "VWCE",
      "current_weight": 34.2,
      "target_weight": 40.0,
      "drift": -5.8
    }
  ],
  "performance": {
    "twr_1y": 6.2,
    "mwr_1y": 5.8
  }
}
```

## Vantaggi di questo approccio

- meno token
- piu' controllo
- meno allucinazioni
- maggiore auditabilita'
- piu' semplicita' nel testing

## Livelli di maturita'

### 1. Explain-only

Il bot:

- spiega KPI
- spiega andamento portafoglio
- interpreta allocazione
- evidenzia drift dal target
- spiega i grafici

### 2. Insight assistant

Il bot:

- trova concentrazioni eccessive
- evidenzia scostamenti rilevanti
- identifica posizioni dominanti
- segnala forte cash drag

### 3. Action helper

Il bot:

- propone check operativi
- suggerisce cosa osservare
- confronta scenari semplici

Non deve ancora scrivere nel DB o eseguire azioni.

### 4. Agentic

Il bot usa tool interni per:

- interrogare i dati in modo mirato
- recuperare performance per periodo
- leggere posizioni e transazioni recenti
- costruire spiegazioni piu' precise

## Approccio agentic corretto

Un agente non deve "sapere tutto in anticipo".

Deve usare strumenti.

### Tool interni consigliati

- `get_portfolio_summary(portfolio_id)`
- `get_portfolio_positions(portfolio_id)`
- `get_portfolio_allocation(portfolio_id)`
- `get_target_allocation(portfolio_id)`
- `get_performance_summary(portfolio_id, period)`
- `get_timeseries(portfolio_id, range)`
- `get_cash_balance(portfolio_id)`
- `get_recent_transactions(portfolio_id, limit)`

### Esempio di comportamento

Utente:

`Sono troppo concentrato?`

Agente:

1. chiama `get_portfolio_allocation`
2. calcola i pesi maggiori
3. controlla eventuale target allocation
4. risponde in linguaggio semplice

## UI consigliata

### Entry points

- bottone flottante o CTA secondaria nel dashboard
- voce nel portfolio header
- accesso da mobile via bottom sheet

### Drawer / chat panel

Messaggi iniziali suggeriti:

- `Riassumi questo portafoglio`
- `Spiega la performance recente`
- `Mostra i rischi di concentrazione`
- `Quanto cash ho disponibile?`
- `Confronta il portafoglio con il target`
- `Spiegami questo grafico`

### Formato risposta

Le risposte dovrebbero avere sezioni corte:

- `Sintesi`
- `Numeri chiave`
- `Cosa osservare`

## Guardrail

Fondamentali per non trasformare il bot in un finto consulente:

- disclaimer: supporto informativo, non consulenza finanziaria
- nessuna promessa di rendimento
- nessun consiglio operativo forte senza contesto adeguato
- nessuna invenzione di dati mancanti
- linguaggio semplice e prudente
- risposta esplicita quando i dati non bastano

## Prompting

### System prompt consigliato

Il modello deve essere istruito a:

- usare solo dati forniti o tool disponibili
- non inventare
- non dare consulenza personalizzata aggressiva
- spiegare in italiano semplice
- citare i numeri usati
- distinguere fatti da interpretazioni

### Esempio di tono

- diretto
- sintetico
- chiaro
- prudente
- informativo

## Integrazione backend consigliata per questo repo

### Nuovi file suggeriti

- `src/backend/app/copilot.py`
- `src/backend/app/copilot_service.py`
- eventuale `src/backend/app/copilot_tools.py`

### Endpoint

```http
POST /api/copilot/chat
Content-Type: application/json
```

Body:

```json
{
  "portfolio_id": 7,
  "message": "Spiegami perche' oggi il portafoglio e' negativo"
}
```

Risposta:

```json
{
  "answer": "Oggi il portafoglio e' in calo dello 0,29%...",
  "used_data": {
    "portfolio_id": 7
  }
}
```

## Flusso server consigliato

1. validazione utente e `portfolio_id`
2. recupero dati base
3. costruzione snapshot
4. invocazione modello OpenAI
5. ritorno risposta formattata

## Tooling agentico consigliato

Se vuoi un vero comportamento agentic, esponi tool controllati dal backend invece di dare al modello un contesto troppo grande.

Pattern:

1. modello riceve domanda utente
2. decide quali tool usare
3. backend esegue tool
4. modello sintetizza la risposta

## MVP consigliato

Per partire bene farei un MVP molto stretto:

1. chat UI minimale
2. endpoint backend dedicato
3. snapshot portfolio sintetico
4. 4-6 tool interni
5. system prompt rigido
6. prompt starter nella UI

## Funzionalita' MVP utili

- riepilogo portafoglio
- lettura allocazione
- spiegazione P/L
- spiegazione day change
- spiegazione cash balance
- evidenza drift target

## V2

Solo dopo che il MVP e' stabile:

- tool calling pieno
- analisi multi-portafoglio
- lettura transazioni recenti
- spiegazione grafici e performance per finestra temporale
- simulazioni semplici

## Cosa eviterei all'inizio

- scrittura nel DB
- raccomandazioni di acquisto/vendita
- ordini automatici
- pianificazione fiscale complessa
- accesso indiscriminato a tutte le transazioni raw

## Esempi di domande da supportare

- `Come sta andando questo portafoglio?`
- `Perche' oggi e' sceso?`
- `Quali posizioni pesano di piu'?`
- `Ho troppo cash fermo?`
- `Sono lontano dal target?`
- `Che cosa mi sta aiutando o penalizzando di piu'?`
- `Spiegami il grafico in parole semplici`

## Scelta consigliata

Partire con un `Portfolio Copilot` informativo e contestuale.

Non un chatbot onnisciente.

Non un consulente automatico.

Un assistente che legge bene i dati del prodotto e li traduce in linguaggio semplice e affidabile.
