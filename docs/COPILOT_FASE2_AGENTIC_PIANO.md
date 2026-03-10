# Fase 2 — Copilot Agentic: Tool Calling per Piccoli Investitori

> Piano operativo per trasformare il Portfolio Copilot da "explain-only" a **agente attivo** con tool calling, focalizzato sull'aiutare persone comuni a capire e ottimizzare piccoli portafogli (5k-100k EUR).

---

## 1. Visione

Il copilot MVP risponde a domande usando uno snapshot statico. Funziona bene, ma ha limiti:

- **Non puo' fare calcoli dinamici** ("quanto devo investire per tornare in target?")
- **Non puo' confrontare scenari** ("cosa cambia se vendo X?")
- **Non puo' accedere a dati on-demand** ("mostrami le ultime transazioni")

La Fase 2 aggiunge **tool calling**: il modello decide autonomamente quali dati servono, li richiede al backend, e sintetizza risposte piu' ricche e azionabili.

### Target utente

Persona non esperta con un piccolo portafoglio di ETF/azioni/fondi che vuole:
- **Capire** cosa sta succedendo (in italiano semplice)
- **Ottimizzare** senza dover fare calcoli a mano
- **Agire** con suggerimenti concreti di ribilanciamento
- **Imparare** concetti finanziari nel contesto dei propri dati

---

## 2. Architettura Agentic

### Flusso con tool calling

```
Utente: "Quanto devo investire per tornare in target?"
    |
    v
Backend: invia messaggio + tool definitions al LLM
    |
    v
LLM decide: chiamo get_target_drift + get_cash_balance
    |
    v
Backend: esegue i tool, restituisce i risultati al LLM
    |
    v
LLM (eventualmente): chiamo calculate_rebalance_orders
    |
    v
Backend: esegue, restituisce risultato
    |
    v
LLM: sintetizza risposta finale con importi concreti
    |
    v
Streaming SSE -> Frontend
```

### Principi architetturali

1. **Max 5 round di tool calling** per richiesta (guardrail anti-loop)
2. **Timeout 30s** per l'intera catena agentica
3. **Read-only**: nessun tool scrive nel DB — mai
4. **Snapshot leggero iniziale**: si mantiene uno snapshot base (portfolio summary) nel system prompt, i tool servono per dati specifici
5. **Fallback graceful**: se un tool fallisce, il modello risponde con i dati che ha
6. **Streaming ibrido**: durante i round di tool calling si inviano eventi di stato ("sto analizzando..."), lo streaming testo parte alla risposta finale

---

## 3. Tool Definitions

### 3.1 Tool informativi (dati esistenti)

Questi tool espongono dati gia' disponibili nel repository.

| # | Tool | Descrizione per il modello | Dati restituiti |
|---|---|---|---|
| T1 | `get_portfolio_summary` | Riepilogo generale: valore, costo, P&L, cash | `{ market_value, cost_basis, unrealized_pl, unrealized_pl_pct, day_change, day_change_pct, cash_balance, base_currency }` |
| T2 | `get_positions` | Lista posizioni con peso, valore e performance | `[{ symbol, name, weight, market_value, cost_basis, unrealized_pl_pct, day_change_pct, quantity }]` (max 30) |
| T3 | `get_target_drift` | Scostamento di ogni posizione dal peso target | `[{ symbol, current_weight, target_weight, drift, market_value }]` |
| T4 | `get_performance` | Performance portafoglio per periodo | `{ twr_1m, twr_3m, twr_ytd, twr_1y }` (in %) |
| T5 | `get_cash_balance` | Saldo cash dettagliato | `{ total_cash, breakdown_by_currency[] }` |
| T6 | `get_recent_transactions` | Ultime N transazioni | `[{ date, type, symbol, quantity, price, total, currency }]` (max 20) |
| T7 | `get_portfolio_health` | Score salute portafoglio e alert | `{ score, risk_level, diversification, max_position_weight, alerts[], suggestions[] }` |
| T8 | `get_day_movers` | Best e worst performer del giorno | `{ best: { symbol, pct }, worst: { symbol, pct } }` |
| T9 | `get_monte_carlo` | Proiezioni Monte Carlo a 1-10 anni | `{ mean_return, volatility, projections: [{ year, p25, p50, p75 }] }` |

### 3.2 Tool di calcolo (logica nuova)

Questi tool eseguono calcoli server-side che il modello non potrebbe fare da solo con precisione.

| # | Tool | Descrizione per il modello | Input | Output |
|---|---|---|---|---|
| T10 | `calculate_rebalance_orders` | Calcola gli ordini necessari per tornare al target | `{ available_cash?: float }` | `[{ symbol, action: "buy"|"sell", amount_eur, shares_approx, reason }]` |
| T11 | `calculate_what_if` | Simula l'effetto di un'operazione sul portafoglio | `{ action: "buy"|"sell", symbol: str, amount_eur: float }` | `{ new_weight, old_weight, new_drift, impact_on_diversification }` |
| T12 | `calculate_pac_contribution` | Calcola come distribuire un PAC mensile secondo il target | `{ monthly_amount: float }` | `[{ symbol, amount_eur, shares_approx, new_weight_after }]` |
| T13 | `search_asset_info` | Cerca informazioni su un asset per simbolo | `{ symbol: str }` | `{ name, type, currency, sector, last_price, ter }` |

---

## 4. Domande tipo abilitate dai tool

### Capire il portafoglio (utente base)

| Domanda utente | Tool usati | Risposta tipo |
|---|---|---|
| "Come sta andando il mio portafoglio?" | T1, T4 | Sintesi valore, P&L, performance periodi |
| "Perche' oggi e' sceso?" | T1, T8, T2 | Day change + best/worst + posizioni in calo |
| "Quali sono le mie posizioni piu' grandi?" | T2 | Top 5 per peso con valori |
| "Ho troppo cash fermo?" | T5, T1 | Cash vs valore totale + suggerimento |
| "Cosa ha fatto il portafoglio quest'anno?" | T4 | TWR YTD con contesto |
| "Il mio portafoglio e' sano?" | T7 | Score, alert, suggerimenti |
| "Mostrami le ultime operazioni" | T6 | Lista transazioni recenti |

### Ottimizzare il portafoglio (utente che vuole agire)

| Domanda utente | Tool usati | Risposta tipo |
|---|---|---|
| "Sono lontano dal target?" | T3 | Tabella drift con posizioni sotto/sovra-pesate |
| "Quanto devo investire per tornare in target?" | T3, T5, T10 | Ordini concreti con importi |
| "Cosa succede se vendo 1000 EUR di VWCE?" | T11, T2, T3 | Simulazione impatto su pesi e diversificazione |
| "Ho 200 EUR al mese, come li distribuisco?" | T12, T3 | Piano PAC con distribuzione ottimale |
| "Dovrei ribilanciare ora?" | T3, T7, T10 | Analisi drift + calcolo ordini se necessario |
| "Cos'e' un ETF? Spiegamelo col mio portafoglio" | T2, T13 | Spiegazione didattica usando i suoi dati reali |

### Proiezioni (utente curioso)

| Domanda utente | Tool usati | Risposta tipo |
|---|---|---|
| "Quanto potrebbe valere tra 5 anni?" | T9 | Proiezioni Monte Carlo con P25/P50/P75 |
| "Qual e' il rischio del mio portafoglio?" | T7, T9 | Score rischio + volatilita' + scenario peggiore |

---

## 5. Implementazione Backend

### 5.1 Nuovo file: `src/backend/app/copilot_tools.py` (~350 righe)

Contiene:

1. **Definizioni tool** in formato universale (convertite per ogni provider)
2. **Executor** che mappa tool_name -> funzione Python
3. **Funzioni di calcolo** per T10, T11, T12

```python
# Struttura del file

TOOL_DEFINITIONS = [
    {
        "name": "get_portfolio_summary",
        "description": "Ottieni il riepilogo del portafoglio: valore di mercato, costo, P&L, cash disponibile",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_positions",
        "description": "Ottieni la lista delle posizioni attuali con peso, valore e performance",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ... altri tool ...
    {
        "name": "calculate_rebalance_orders",
        "description": "Calcola gli ordini di acquisto/vendita necessari per riallineare il portafoglio al target. "
                       "Usa questo tool quando l'utente chiede come ribilanciare o tornare in target.",
        "parameters": {
            "type": "object",
            "properties": {
                "available_cash": {
                    "type": "number",
                    "description": "Cash aggiuntivo da investire (opzionale, default: usa cash disponibile nel portafoglio)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "calculate_what_if",
        "description": "Simula l'effetto di un'operazione (acquisto o vendita) sui pesi e la diversificazione del portafoglio.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["buy", "sell"]},
                "symbol": {"type": "string", "description": "Simbolo dell'asset (es. VWCE.DE)"},
                "amount_eur": {"type": "number", "description": "Importo in EUR dell'operazione"},
            },
            "required": ["action", "symbol", "amount_eur"],
        },
    },
    {
        "name": "calculate_pac_contribution",
        "description": "Calcola come distribuire un versamento periodico (PAC) tra gli asset del portafoglio per avvicinarsi al target.",
        "parameters": {
            "type": "object",
            "properties": {
                "monthly_amount": {"type": "number", "description": "Importo mensile da investire in EUR"},
            },
            "required": ["monthly_amount"],
        },
    },
]


def execute_tool(
    tool_name: str,
    tool_args: dict,
    repo: PortfolioRepository,
    perf_service: PerformanceService,
    portfolio_id: int,
    user_id: str,
) -> dict:
    """Esegue un tool e restituisce il risultato come dict JSON-serializzabile."""
    ...


def format_tools_for_provider(provider: str) -> list:
    """Converte TOOL_DEFINITIONS nel formato specifico del provider (OpenAI, Anthropic, Gemini)."""
    ...
```

### 5.2 Modifica: `src/backend/app/copilot_service.py`

Aggiungere il **loop agentico** alle funzioni di streaming:

```python
def stream_copilot_response_agentic(
    config: CopilotConfig,
    snapshot: dict,           # snapshot leggero (solo summary)
    messages: list[CopilotMessage],
    repo: PortfolioRepository,
    perf_service: PerformanceService,
    portfolio_id: int,
    user_id: str,
) -> Generator[str, None, None]:
    """Stream con supporto tool calling. Max 5 round."""

    tools = format_tools_for_provider(config.provider)
    system_prompt = SYSTEM_PROMPT_AGENTIC.format(
        context=json.dumps(snapshot, ensure_ascii=False)
    )

    # Loop agentico
    for round_num in range(MAX_TOOL_ROUNDS):
        response = call_llm_with_tools(config, system_prompt, messages, tools)

        if response.has_tool_calls:
            # Emetti evento di stato
            yield sse_event("thinking", f"Sto analizzando i dati ({round_num + 1})...")

            # Esegui ogni tool call
            for tool_call in response.tool_calls:
                result = execute_tool(
                    tool_call.name, tool_call.args,
                    repo, perf_service, portfolio_id, user_id
                )
                messages.append(tool_result_message(tool_call.id, result))

            continue  # altro round

        # Nessun tool call -> streaming risposta finale
        yield from stream_final_response(config, system_prompt, messages)
        break
```

### 5.3 System prompt agentico

```python
SYSTEM_PROMPT_AGENTIC = """\
Sei il Portfolio Copilot di Valore365, un assistente che aiuta persone comuni
a capire e ottimizzare i propri piccoli portafogli di investimento.

Il tuo utente tipico NON e' un professionista della finanza. Parla in modo
semplice, concreto e amichevole. Usa analogie quotidiane quando servono.

Hai accesso a diversi strumenti (tool) per ottenere dati dal portafoglio
dell'utente. Usali quando serve per dare risposte precise e basate sui dati.

Regole:
- Rispondi SOLO in italiano
- Usa SOLO dati ottenuti dai tool o dallo snapshot, MAI inventare numeri
- Non dare consulenza finanziaria personalizzata — dai informazioni e calcoli
- Quando suggerisci operazioni, mostra sempre i numeri concreti (importi, quote)
- Se l'utente chiede qualcosa che non puoi calcolare, dillo onestamente
- Spiega i concetti finanziari in modo semplice quando li usi
  (es. "Il drift e' quanto sei lontano dal tuo piano originale")
- Alla fine aggiungi: "⚠️ Supporto informativo, non consulenza finanziaria."

Formato risposta:
- Vai dritto al punto, niente introduzioni lunghe
- Usa **grassetto** per numeri importanti
- Usa tabelle quando confronti piu' asset
- Se suggerisci azioni, elencale come checklist

Ecco un riepilogo base del portafoglio:

{context}
"""
```

### 5.4 Modifica: `src/backend/app/main.py`

Aggiornare l'endpoint `/api/copilot/chat`:

```python
@app.post("/api/copilot/chat")
async def copilot_chat(
    request: CopilotChatRequest,
    user_id: str = Depends(require_auth_rate_limited),
):
    # ... risoluzione config (invariato) ...

    # Snapshot leggero (solo summary per contesto base)
    snapshot = build_portfolio_snapshot_light(repo, portfolio_id, user_id)

    # Usa il flusso agentico se il provider supporta tool calling
    if config.provider in ("openai", "anthropic", "gemini"):
        generator = stream_copilot_response_agentic(
            config, snapshot, request.messages,
            repo, perf_service, portfolio_id, user_id,
        )
    else:
        # Fallback per provider locali senza tool calling
        full_snapshot = build_portfolio_snapshot(repo, perf_service, portfolio_id, user_id)
        generator = stream_copilot_response(config, full_snapshot, request.messages)

    return StreamingResponse(generator, media_type="text/event-stream", ...)
```

---

## 6. Implementazione Frontend

### 6.1 Modifica: `CopilotChat.tsx`

Gestire il nuovo evento SSE `thinking`:

```typescript
// Parsing eventi SSE — aggiungere tipo "thinking"
if (parsed.type === "thinking") {
  setThinkingStatus(parsed.content);  // "Sto analizzando i dati (1)..."
} else if (parsed.type === "text_delta") {
  setThinkingStatus(null);
  appendToLastMessage(parsed.content);
}
```

UI durante il thinking:
- Mostrare un indicatore sotto l'ultimo messaggio: `"🔍 Sto analizzando i dati..."`
- Animazione pulse/skeleton per indicare che il copilot sta lavorando

### 6.2 Quick prompts aggiornati

Aggiornare i suggerimenti per riflettere le nuove capacita':

```typescript
const QUICK_PROMPTS = [
  { label: "Riassumi il portafoglio", icon: "📊" },
  { label: "Sono lontano dal target?", icon: "🎯" },
  { label: "Quanto devo investire per ribilanciare?", icon: "⚖️" },
  { label: "Ho 200€/mese, come li distribuisco?", icon: "💰" },
  { label: "Il mio portafoglio e' sano?", icon: "🩺" },
  { label: "Cosa succede se vendo il titolo piu' pesante?", icon: "🔮" },
];
```

---

## 7. Logica di calcolo dei tool computazionali

### T10: `calculate_rebalance_orders`

```
Input: available_cash (opzionale)
Logica:
  1. Prendi drift da target per ogni posizione
  2. Cash disponibile = parametro || cash_balance del portafoglio
  3. Per ogni posizione con drift negativo (sotto-pesata):
     - amount_to_buy = drift_pct * (market_value + available_cash) / 100
     - Limita a cash disponibile rimanente
  4. Per posizioni sovra-pesate (se l'utente non ha cash):
     - amount_to_sell = |drift_pct| * market_value / 100
  5. Ordina per drift assoluto decrescente (priorita' alle deviazioni maggiori)
  6. Calcola shares_approx = amount / last_price

Output: lista ordini con { symbol, action, amount_eur, shares_approx, reason }
```

### T11: `calculate_what_if`

```
Input: action, symbol, amount_eur
Logica:
  1. Prendi posizioni attuali e valore totale
  2. Simula l'operazione:
     - buy: new_value = old_value + amount; total += amount
     - sell: new_value = old_value - amount; total -= amount
  3. Ricalcola tutti i pesi
  4. Confronta con target se presente
  5. Calcola impatto su max_position_weight (concentrazione)

Output: { old_weight, new_weight, old_drift, new_drift, impact_on_diversification }
```

### T12: `calculate_pac_contribution`

```
Input: monthly_amount
Logica:
  1. Prendi target allocation
  2. Prendi drift attuale
  3. Distribuisci il monthly_amount dando priorita' alle posizioni
     piu' sotto-pesate rispetto al target
  4. Per ogni asset: calcola shares_approx = allocated_amount / last_price
  5. Calcola il peso risultante dopo l'investimento

Output: [{ symbol, amount_eur, shares_approx, current_weight, new_weight_after }]
```

---

## 8. Conversione tool per provider

### OpenAI

```python
{
    "type": "function",
    "function": {
        "name": "get_positions",
        "description": "...",
        "parameters": { ... }
    }
}
```

### Anthropic

```python
{
    "name": "get_positions",
    "description": "...",
    "input_schema": { ... }
}
```

### Gemini

```python
# google-genai usa lo stesso formato OpenAI-like
{
    "name": "get_positions",
    "description": "...",
    "parameters": { ... }
}
```

---

## 9. Guardrail e sicurezza

| Guardrail | Implementazione |
|---|---|
| Max round tool calling | `MAX_TOOL_ROUNDS = 5` — dopo 5 round il modello deve rispondere |
| Timeout totale | 30 secondi per l'intera catena request → response |
| Read-only | Nessun tool ha accesso a metodi di scrittura del repository |
| Multi-tenant | `portfolio_id` + `user_id` passati a ogni tool execution |
| Validazione input tool | Pydantic validation sugli argomenti prima dell'esecuzione |
| Rate limiting | Mantenere il limite esistente (120 req/60s per utente) |
| Cost control | Snapshot leggero (meno token nel system prompt) + tool on-demand |
| Fallback | Se tool calling fallisce, il copilot usa lo snapshot statico come oggi |

---

## 10. Sequenza operativa di sviluppo

```
Passo  File                                           Azione
-----  ---------------------------------------------  -------------------------------------------
  1    src/backend/app/copilot_tools.py                NUOVO: definizioni tool + executor + calcoli
  2    src/backend/app/copilot_service.py              MODIFICA: aggiungere loop agentico +
                                                                 prompt agentico +
                                                                 streaming con tool rounds
  3    src/backend/app/main.py                         MODIFICA: aggiornare endpoint /copilot/chat
                                                                 per usare flusso agentico
  4    src/frontend/.../copilot/CopilotChat.tsx        MODIFICA: gestire evento "thinking" +
                                                                 aggiornare quick prompts
  5    src/frontend/.../copilot/MessageBubble.tsx      MODIFICA: aggiungere stato "thinking"
                                                                 con indicatore animato
  6    docs/PORTFOLIO_COPILOT_PIANO_CLAUDE.md          MODIFICA: aggiornare stato Fase 2
```

**Nessuna nuova dipendenza** — le librerie dei provider (openai, anthropic, google-genai) supportano gia' tool calling.

**Nessuna migrazione DB** — i tool sono read-only e usano dati esistenti.

---

## 11. Test e verifica

| # | Test | Verifica |
|---|---|---|
| 1 | Tool singolo | Chiamata diretta a `execute_tool("get_positions", ...)` restituisce dati corretti |
| 2 | Loop agentico | Domanda "quanto devo investire per ribilanciare?" attiva almeno 2 tool call |
| 3 | Max rounds | Dopo 5 round il modello smette di chiamare tool e risponde |
| 4 | Timeout | Richieste che superano 30s restituiscono errore graceful |
| 5 | Fallback locale | Provider "local" senza tool calling usa snapshot statico |
| 6 | What-if corretto | `calculate_what_if(buy, VWCE, 1000)` restituisce pesi coerenti |
| 7 | Rebalance corretto | `calculate_rebalance_orders()` non suggerisce ordini > cash disponibile |
| 8 | PAC distribuzione | `calculate_pac_contribution(200)` somma degli importi = 200 EUR |
| 9 | Multi-tenant | Tool eseguiti con user_id A non restituiscono dati di user_id B |
| 10 | Frontend thinking | Indicatore "Sto analizzando..." visibile durante tool rounds |
| 11 | Streaming finale | Risposta testuale arriva in streaming dopo i tool rounds |
| 12 | Provider switching | Tool calling funziona con OpenAI, Anthropic e Gemini |

---

## 12. Metriche di successo

Per un piccolo investitore, il copilot agentico ha successo se:

- **Ribilanciamento in 1 domanda**: l'utente chiede "come ribilancio?" e riceve ordini concreti con importi
- **PAC ottimizzato**: l'utente dice quanto investe al mese e riceve la distribuzione ottimale
- **Zero calcoli manuali**: niente fogli Excel, il copilot fa tutto
- **Comprensione**: l'utente capisce il "perche'" dietro ogni suggerimento
- **Fiducia nei dati**: ogni numero citato corrisponde ai dati reali del portafoglio

---

## 13. Cosa NON fare nella Fase 2

- **No ordini automatici** — il copilot suggerisce, l'utente esegue
- **No raccomandazioni di asset specifici** — non suggerisce "compra X" se non e' gia' nel portafoglio/target
- **No previsioni di prezzo** — Monte Carlo si', ma crystal ball no
- **No persistenza conversazioni** — rimandato a Fase 3
- **No multi-portafoglio** — un portafoglio per conversazione, rimandato a Fase 3
