# Piano Implementativo: Portfolio Copilot — Multi-Provider LLM

> Piano operativo per l'integrazione di un chatbot agentic multi-provider in Valore365, con supporto finanziario contestuale per ciascun portafoglio.

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
    +-- build_portfolio_snapshot(repo, perf_service, portfolio_id, user_id)
    |       |-- repo.get_summary()              -> valore, P&L, cash
    |       |-- repo.get_positions()             -> posizioni attuali
    |       |-- repo.get_allocation()            -> pesi correnti
    |       |-- repo.list_target_allocations()   -> pesi target + drift
    |       |-- repo.get_target_performance()    -> best/worst performer
    |       |-- perf_service.get_performance_summary()  -> TWR per periodo
    |       +-> snapshot JSON compatto (~1-2K token)
    |
    +-- SYSTEM_PROMPT + snapshot -> LLM provider (OpenAI / Anthropic / Gemini)
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

### Fase 1 — MVP: Explain-only ✅ COMPLETATA

Il copilot riceve uno snapshot statico e risponde. Nessun tool calling.
Supporto multi-provider (OpenAI, Anthropic, Google Gemini) implementato fin da subito.

#### 3.1 Backend

**File creati:**

| File | Contenuto | Righe |
|---|---|---|
| `src/backend/app/copilot_service.py` | Modelli Pydantic, snapshot builder, system prompt, streaming multi-provider | ~210 |

**File modificati:**

| File | Modifica |
|---|---|
| `src/backend/app/config.py` | Aggiunte env vars: `COPILOT_PROVIDER`, `COPILOT_MODEL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` |
| `src/backend/app/main.py` | Aggiunti `POST /api/copilot/chat` e `GET /api/copilot/status` |
| `src/backend/requirements.txt` | Aggiunti `openai>=1.40.0`, `anthropic>=0.39.0`, `google-genai>=1.0.0` |

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
    "market_value": 104230.12, "cost_basis": 95810.01,
    "unrealized_pl": 8420.11, "unrealized_pl_pct": 8.78,
    "day_change": -312.4, "day_change_pct": -0.29,
    "cash_balance": 5120.44
  },
  "positions": [
    {"symbol": "VWCE", "name": "Vanguard FTSE All-World", "weight": 34.2, "market_value": 35600, "unrealized_pl_pct": 12.3, "day_change_pct": -0.4}
  ],
  "target_drift": [
    {"symbol": "VWCE", "current_weight": 34.2, "target_weight": 40.0, "drift": -5.8}
  ],
  "performance": {
    "twr_1m": 1.2, "twr_3m": 3.4, "twr_ytd": 5.1, "twr_1y": 6.2
  },
  "best_performer": {"symbol": "NVDA", "day_change_pct": 3.2},
  "worst_performer": {"symbol": "AGGH", "day_change_pct": -1.1}
}
```

Troncato a max 30 posizioni ordinate per peso. Totale stimato: 800-1500 token.

**System prompt implementato:**

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
- Alla fine aggiungi: "⚠️ Supporto informativo, non consulenza finanziaria."

Formato risposta consigliato:
- **Sintesi** (2-3 frasi)
- **Numeri chiave** (lista breve)
- **Cosa osservare** (se pertinente)
```

**Multi-provider streaming implementato:**

| Provider | Funzione | Libreria | Default model |
|---|---|---|---|
| OpenAI | `_stream_openai()` | `openai` | `gpt-4o-mini` |
| Anthropic | `_stream_anthropic()` | `anthropic` | `claude-sonnet-4-20250514` |
| Google Gemini | `_stream_gemini()` | `google-genai` | `gemini-2.0-flash` |

#### 3.2 Frontend

**File creati:**

| File | Contenuto | Righe |
|---|---|---|
| `src/frontend/.../components/copilot/CopilotChat.tsx` | Drawer chat con streaming SSE, quick prompts | ~230 |
| `src/frontend/.../components/copilot/MessageBubble.tsx` | Bolle messaggio user/assistant con dark/light mode | ~65 |

**File modificati:**

| File | Modifica |
|---|---|
| `src/frontend/.../services/api.ts` | Tipi `CopilotStatus`, funzione `getCopilotStatus()`, export `getAuthToken()` |
| `src/frontend/.../pages/Dashboard.page.tsx` | FAB button teal + `<CopilotChat>` drawer + stato `copilotAvailable` |

**UI implementata:**
- **FAB button** fisso in basso a destra con icona robot (teal), visibile solo se copilot configurato
- **Desktop**: Drawer Mantine da destra, `size="lg"`
- **Mobile**: stesso FAB posizionato sopra la bottom nav (`bottom: 80px`)
- **Chat**: `ScrollArea` con auto-scroll, messaggi user (blu) e assistant (grigio) con avatar robot
- **Quick prompts** (6 suggerimenti) mostrati a chat vuota
- **Input**: `Textarea` con invio su Enter + bottone send
- **AbortController** per cancellare stream alla chiusura
- **Reset** automatico della conversazione al cambio portfolio
- **Bottone cestino** per cancellare manualmente la conversazione

---

### Fase 2 — Agentic: Tool Calling (da fare)

Il modello puo' richiedere dati specifici tramite function/tool calling del provider.

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
- Usare il parametro `tools` di ciascun provider (OpenAI, Anthropic, Gemini supportano tutti tool calling)
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

---

## 4. Configurazione

Variabili d'ambiente backend:

```bash
# Provider LLM: "openai" | "anthropic" | "gemini" (default: openai)
COPILOT_PROVIDER=openai

# API keys — serve solo quella del provider scelto
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AI...

# Modello — opzionale, usa default per provider se vuoto
COPILOT_MODEL=
```

**Modelli default per provider:**

| Provider | Modello default | Pro | Costo stimato |
|---|---|---|---|
| `openai` | `gpt-4o-mini` | Veloce, economico | ~0.001$ per domanda |
| `anthropic` | `claude-sonnet-4-20250514` | Ottimo ragionamento | ~0.005$ per domanda |
| `gemini` | `gemini-2.0-flash` | Veloce, gratuito per bassi volumi | ~0.001$ per domanda |

Modelli alternativi configurabili via `COPILOT_MODEL`:
- OpenAI: `gpt-4o`, `gpt-4.1-mini`, `gpt-4.1`
- Anthropic: `claude-opus-4-20250514`, `claude-haiku-4-5-20251001`
- Gemini: `gemini-2.5-pro`, `gemini-2.5-flash`

Frontend: nessuna nuova variabile necessaria (usa `VITE_API_BASE_URL` esistente).

Se la API key del provider selezionato non e' configurata, il FAB button non appare nel frontend.

---

## 5. Sicurezza e guardrail

### Multi-tenant ✅ Implementato
- Ogni chiamata passa per `require_auth` -> `user_id`
- Lo snapshot viene costruito filtrando sempre per `owner_user_id`
- Nessun accesso cross-utente possibile

### Prompt injection ✅ Implementato
- Lo snapshot e' costruito dal backend, non dall'utente
- I messaggi utente vengono passati come `user` role, mai nel system prompt
- Il system prompt istruisce il modello a usare solo dati forniti

### Disclaimer ✅ Implementato
- Il system prompt impone il disclaimer a fine risposta
- "⚠️ Supporto informativo, non consulenza finanziaria."

### Rate limiting (da fare)
- Limitare a 20 messaggi/minuto per utente (implementabile con middleware FastAPI)
- Max 10 messaggi per conversazione (reset automatico)

---

## 6. Sequenza operativa di sviluppo

```
Passo  File                                           Azione                              Stato
-----  ---------------------------------------------  ----------------------------------  -----
  1    src/backend/requirements.txt                    + openai, anthropic, google-genai   ✅
  2    src/backend/app/config.py                       + COPILOT_PROVIDER, API keys        ✅
  3    src/backend/app/copilot_service.py              NUOVO: snapshot, prompt, streaming  ✅
  4    src/backend/app/main.py                         + 2 endpoint copilot                ✅
  5    src/frontend/.../services/api.ts                + tipi, getCopilotStatus(), token   ✅
  6    src/frontend/.../copilot/MessageBubble.tsx       NUOVO: componente messaggio        ✅
  7    src/frontend/.../copilot/CopilotChat.tsx         NUOVO: drawer chat + SSE           ✅
  8    src/frontend/.../pages/Dashboard.page.tsx        + FAB button + render CopilotChat  ✅
```

**Commit**: `c14ffd8` — "Implement Portfolio Copilot MVP with multi-provider LLM support"

---

## 7. Test e verifica

| # | Test | Comando/Azione | Stato |
|---|---|---|---|
| 1 | Backend health | `GET /api/copilot/status` -> `{"available": true}` | da testare |
| 2 | Streaming SSE | `curl -N -X POST /api/copilot/chat -H 'Content-Type: application/json' -d '{"portfolio_id":1,"messages":[{"role":"user","content":"riassumi"}]}'` | da testare |
| 3 | Senza API key | `GET /api/copilot/status` -> `{"available": false}` | da testare |
| 4 | Portfolio inesistente | Deve restituire 404, non errore del modello | da testare |
| 5 | UI desktop | FAB visibile, drawer si apre, streaming funziona | da testare |
| 6 | UI mobile | FAB sopra bottom nav, drawer si apre, scroll corretto | da testare |
| 7 | Quick prompts | Click su suggerimento -> invia messaggio automaticamente | da testare |
| 8 | Cambio portfolio | Conversazione si resetta | da testare |
| 9 | Multi-tenant | Utente A non vede dati di utente B | da testare |
| 10 | Accuratezza | Numeri citati dal copilot corrispondono ai dati reali | da testare |
| 11 | Multi-provider | Testare switch tra openai/anthropic/gemini | da testare |
| 12 | TypeScript | `npx tsc --noEmit` passa senza errori | ✅ |

---

## 8. Domande tipo supportate nel MVP

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
- Persistenza conversazioni su DB
