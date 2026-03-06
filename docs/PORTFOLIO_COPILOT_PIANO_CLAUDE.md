# Piano Implementativo: Portfolio Copilot — ChatGPT Agentic

> Piano operativo per l'integrazione di un chatbot agentic basato su OpenAI (ChatGPT) in Valore365, con supporto finanziario contestuale per ciascun portafoglio.

---

## 1. Obiettivo

Un **Portfolio Copilot** che:

- spiega in linguaggio semplice come sta andando un portafoglio
- interpreta KPI, allocazione, drift dal target, performance
- risponde a domande come "perche' oggi e' sceso?", "sono troppo concentrato?", "quanto cash ho?"
- **non** da' consulenza finanziaria personalizzata
- **non** esegue azioni (no scrittura DB, no ordini)

---

## 2. Architettura

```
Utente digita messaggio nella chat UI
    |
    v
Frontend: POST /api/copilot/chat { portfolio_id, messages[] }
    |                                (con JWT Clerk)
    v
Backend (FastAPI):
    |
    +-- require_auth --> user_id (multi-tenant)
    |
    +-- build_portfolio_snapshot(repo, portfolio_id, user_id)
    |       |-- repo.get_summary()              -> valore, P&L, cash
    |       |-- repo.get_positions()             -> posizioni attuali
    |       |-- repo.get_allocation()            -> pesi correnti
    |       |-- repo.list_target_allocations()   -> pesi target + drift
    |       |-- repo.get_target_performance()    -> best/worst performer
    |       |-- performance_service.summary()    -> TWR/MWR per periodo
    |       |-- repo.get_cash_balance()          -> cash per valuta
    |       +-> snapshot JSON compatto (~1-2K token)
    |
    +-- SYSTEM_PROMPT + snapshot -> OpenAI Chat Completions API (stream)
    |
    v
StreamingResponse (SSE text/event-stream)
    |
    v
Frontend: ReadableStream reader -> messaggi in tempo reale
```

**Principio chiave**: il modello non accede mai al DB. Il backend costruisce uno snapshot controllato e lo inietta nel system prompt. Meno token, meno allucinazioni, piu' auditabilita'.

---

## 3. Fasi di implementazione

### Fase 1 — MVP: Explain-only (stima ~500 righe nuove)

Il copilot riceve uno snapshot statico e risponde. Nessun tool calling.

#### 3.1 Backend

**File nuovi:**

| File | Contenuto | Righe stimate |
|---|---|---|
| `src/backend/app/copilot_service.py` | Modelli Pydantic, snapshot builder, system prompt, streaming | ~150 |

**File modificati:**

| File | Modifica |
|---|---|
| `src/backend/app/config.py` | Aggiungere `OPENAI_API_KEY`, `COPILOT_MODEL` (default: `gpt-4o-mini`) |
| `src/backend/app/main.py` | Aggiungere `POST /api/copilot/chat` e `GET /api/copilot/status` |
| `src/backend/requirements.txt` | Aggiungere `openai>=1.40.0` |

**Endpoint `POST /api/copilot/chat`:**

```python
# Request
{
  "portfolio_id": 7,
  "messages": [
    {"role": "user", "content": "Come sta andando il mio portafoglio?"}
  ]
}

# Response: SSE stream
data: {"type": "text_delta", "content": "Il tuo"}
data: {"type": "text_delta", "content": " portafoglio"}
data: {"type": "done", "content": ""}
```

**Endpoint `GET /api/copilot/status`:**

```json
{"available": true, "provider": "openai", "model": "gpt-4o-mini"}
```

**Snapshot strutturato (iniettato nel system prompt):**

```json
{
  "portfolio": {
    "name": "ETF Core", "base_currency": "EUR",
    "market_value": 104230.12, "cash_balance": 5120.44,
    "unrealized_pl": 8420.11, "unrealized_pl_pct": 8.78,
    "day_change": -312.4, "day_change_pct": -0.29
  },
  "positions": [
    {"symbol": "VWCE", "weight": 34.2, "market_value": 35600, "unrealized_pl_pct": 12.3, "day_change_pct": -0.4},
    ...
  ],
  "target_drift": [
    {"symbol": "VWCE", "current_weight": 34.2, "target_weight": 40.0, "drift": -5.8},
    ...
  ],
  "performance": {
    "twr_1m": 1.2, "twr_3m": 3.4, "twr_ytd": 5.1, "twr_1y": 6.2
  },
  "cash": {
    "total": 5120.44,
    "breakdown": [{"currency": "EUR", "balance": 5120.44}]
  },
  "best_performer": {"symbol": "NVDA", "day_change_pct": 3.2},
  "worst_performer": {"symbol": "AGGH", "day_change_pct": -1.1}
}
```

Troncato a max 30 posizioni ordinate per peso. Totale stimato: 800-1500 token.

**System prompt:**

```
Sei il Portfolio Copilot di Valore365, un assistente informativo per investitori.

Regole:
- Rispondi SOLO in italiano
- Usa SOLO i dati forniti nello snapshot, non inventare mai numeri o fatti
- Non dare consulenza finanziaria personalizzata
- Se non hai dati sufficienti, dillo esplicitamente
- Sii sintetico, diretto e chiaro
- Cita sempre i numeri quando li usi
- Distingui fatti da interpretazioni
- Aggiungi sempre il disclaimer: "Questo e' un supporto informativo, non consulenza finanziaria."

Formato risposta consigliato:
- Sintesi (2-3 frasi)
- Numeri chiave (lista breve)
- Cosa osservare (se pertinente)

Ecco i dati del portafoglio dell'utente:
{snapshot}
```

#### 3.2 Frontend

**File nuovi:**

| File | Contenuto | Righe stimate |
|---|---|---|
| `src/frontend/.../components/copilot/CopilotChat.tsx` | Drawer chat con streaming SSE | ~200 |
| `src/frontend/.../components/copilot/MessageBubble.tsx` | Singolo messaggio (user/assistant) | ~60 |

**File modificati:**

| File | Modifica |
|---|---|
| `src/frontend/.../services/api.ts` | Tipi `CopilotMessage`, `CopilotStatus`, funzione `getCopilotStatus()`, export token getter |
| `src/frontend/.../pages/Dashboard.page.tsx` | Bottone FAB + render `<CopilotChat>` |

**UI — Desktop:**
- Bottone con icona sparkles nell'header, accanto al bottone Aggiorna
- Apre un `Drawer` Mantine da destra, `size="lg"`

**UI — Mobile:**
- Stesso bottone nell'header mobile (DashboardMobileHeader)
- Drawer full-screen (`size="100%"`)

**Componente CopilotChat:**
- `ScrollArea` con lista messaggi e auto-scroll
- `Textarea` + bottone invio in basso (invio anche con Enter)
- Quick prompts quando la chat e' vuota:
  - "Riassumi questo portafoglio"
  - "Perche' oggi e' in calo?"
  - "Mostra i rischi di concentrazione"
  - "Quanto cash ho disponibile?"
  - "Quanto sono lontano dal target?"
- Stato locale: `messages[]`, `input`, `streaming`, `error`
- `AbortController` per cancellare stream alla chiusura
- Reset conversazione al cambio portfolio

**Streaming SSE (no EventSource, fetch diretto):**

```typescript
const res = await fetch(`${API_URL}/copilot/chat`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
  body: JSON.stringify({ portfolio_id, messages }),
});
const reader = res.body!.getReader();
const decoder = new TextDecoder();
// parse SSE chunks, append text_delta to last assistant message
```

---

### Fase 2 — Agentic: Tool Calling (dopo stabilizzazione MVP)

Il modello puo' richiedere dati specifici tramite OpenAI function calling.

**Tool interni esposti al modello:**

| Tool | Descrizione | Dati restituiti |
|---|---|---|
| `get_portfolio_summary` | Riepilogo portafoglio | Valore, P&L, cash |
| `get_positions` | Posizioni attuali | Lista con peso, valore, P&L |
| `get_allocation` | Allocazione corrente | Pesi percentuali |
| `get_target_drift` | Scostamento dal target | Drift per asset |
| `get_performance` | Performance per periodo | TWR/MWR per 1m/3m/6m/ytd/1y |
| `get_cash_balance` | Saldo cash | Totale e breakdown per valuta |
| `get_recent_transactions` | Ultime N transazioni | Data, tipo, importo, asset |
| `get_day_movers` | Best/worst del giorno | Simbolo e variazione % |

**Flusso agentic:**

```
Utente: "Sono troppo concentrato?"
    |
    v
Modello decide: chiamo get_allocation
    |
    v
Backend esegue get_allocation(portfolio_id, user_id) -> risultato
    |
    v
Modello riceve risultato, eventualmente chiama get_target_drift
    |
    v
Modello sintetizza risposta finale
```

**Implementazione:**
- Usare il parametro `tools` di OpenAI Chat Completions
- Backend gestisce il loop tool_calls -> esecuzione -> risposta
- Max 3 round di tool calling per richiesta (guardrail)
- Streaming della risposta finale

---

### Fase 3 — Evoluzioni future (V2)

Solo dopo che Fase 1 + 2 sono stabili:

- Analisi multi-portafoglio ("confronta i miei due portafogli")
- Spiegazione grafici (il frontend invia metadata del grafico visibile)
- Simulazioni semplici ("cosa succede se vendo VWCE?")
- Storico conversazioni persistente (DB)
- Scelta provider multi-LLM (Anthropic/OpenAI) come in PIANO_AI_ADVISOR_AGENT

---

## 4. Configurazione

Variabili d'ambiente da aggiungere:

```bash
# .env backend
OPENAI_API_KEY=sk-...
COPILOT_MODEL=gpt-4o-mini    # oppure gpt-4o per risposte migliori
```

| Modello | Pro | Contro | Costo stimato |
|---|---|---|---|
| `gpt-4o-mini` | Veloce, economico (~0.15$/1M input) | Meno preciso su analisi complesse | ~0.001$ per domanda |
| `gpt-4o` | Piu' capace, ragionamento migliore | 10x piu' costoso | ~0.01$ per domanda |

Consiglio: partire con `gpt-4o-mini` per il MVP, passare a `gpt-4o` se la qualita' non e' sufficiente.

Frontend:

```bash
# .env frontend (nessuna nuova variabile necessaria)
# Il copilot usa lo stesso VITE_API_BASE_URL del resto dell'app
```

---

## 5. Sicurezza e guardrail

### Multi-tenant
- Ogni chiamata passa per `require_auth` -> `user_id`
- Lo snapshot viene costruito filtrando sempre per `owner_user_id`
- Nessun accesso cross-utente possibile

### Prompt injection
- Lo snapshot e' costruito dal backend, non dall'utente
- I messaggi utente vengono passati come `user` role, mai nel system prompt
- Il system prompt istruisce il modello a ignorare istruzioni contraddittorie

### Rate limiting
- Limitare a 20 messaggi/minuto per utente (implementabile con middleware FastAPI)
- Max 10 messaggi per conversazione (reset automatico)

### Disclaimer
- Ogni risposta deve contenere il disclaimer informativo
- Il system prompt lo impone
- Il frontend puo' aggiungerlo come footer fisso nel drawer

---

## 6. Sequenza operativa di sviluppo

```
Passo  File                                      Azione
-----  ----------------------------------------  ---------------------------
  1    src/backend/requirements.txt               + openai>=1.40.0
  2    src/backend/app/config.py                  + OPENAI_API_KEY, COPILOT_MODEL
  3    src/backend/app/copilot_service.py          NUOVO: snapshot, prompt, streaming
  4    src/backend/app/main.py                    + 2 endpoint (/copilot/chat, /copilot/status)
  5    src/frontend/.../services/api.ts           + tipi, getCopilotStatus(), export token
  6    src/frontend/.../copilot/MessageBubble.tsx  NUOVO: componente messaggio
  7    src/frontend/.../copilot/CopilotChat.tsx    NUOVO: drawer chat + SSE
  8    src/frontend/.../pages/Dashboard.page.tsx  + bottone FAB + render CopilotChat
```

---

## 7. Test e verifica

| # | Test | Comando/Azione |
|---|---|---|
| 1 | Backend health | `GET /api/copilot/status` -> `{"available": true}` |
| 2 | Streaming SSE | `curl -N -X POST /api/copilot/chat -d '{"portfolio_id":1,"messages":[{"role":"user","content":"riassumi"}]}'` |
| 3 | Senza API key | `GET /api/copilot/status` -> `{"available": false}` |
| 4 | Portfolio inesistente | Deve restituire 404, non errore del modello |
| 5 | UI desktop | Bottone visibile, drawer si apre, streaming funziona |
| 6 | UI mobile | Drawer full-screen, input funziona, scroll corretto |
| 7 | Quick prompts | Click su suggerimento -> invia messaggio automaticamente |
| 8 | Cambio portfolio | Conversazione si resetta |
| 9 | Multi-tenant | Utente A non vede dati di utente B |
| 10 | Accuratezza | Numeri citati dal copilot corrispondono ai dati reali nel dashboard |

---

## 8. Domande tipo da supportare nel MVP

- "Come sta andando il mio portafoglio?"
- "Perche' oggi e' sceso?"
- "Quali posizioni pesano di piu'?"
- "Ho troppo cash fermo?"
- "Sono lontano dal target?"
- "Qual e' la mia performance da inizio anno?"
- "Chi sta andando meglio e chi peggio oggi?"
- "Spiegami i KPI in parole semplici"

---

## 9. Cosa NON fare nel MVP

- Scrittura nel DB
- Raccomandazioni di acquisto/vendita
- Ordini automatici
- Pianificazione fiscale
- Accesso a tutte le transazioni raw
- Multi-provider LLM (solo OpenAI per ora)
- Persistenza conversazioni su DB
