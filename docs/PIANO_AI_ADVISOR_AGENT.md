# Piano: AI Portfolio Advisor Agent per Valore365

## Contesto

Valore365 è un portfolio tracker SaaS (FastAPI + React/Mantine + PostgreSQL) che già gestisce portafogli target con allocazioni, drift analysis e ribilanciamento manuale. L'utente vuole aggiungere un **agente AI conversazionale** (Claude API) che fornisca consigli sia di ribilanciamento che di ottimizzazione del target, accessibile tramite una **chat sidebar** nell'interfaccia.

---

## Architettura

```
User digita messaggio in AdvisorChat (Drawer destro)
    │
    ▼
POST /api/advisor/chat  { portfolio_id, messages[] }
    │
    ▼
Backend: require_auth → user_id (multi-tenant sicuro)
    │
    ▼
build_portfolio_context(repo, portfolio_id, user_id)
    │   ├─ repo.get_summary()          → valore, P&L, cash
    │   ├─ repo.get_positions()        → posizioni attuali
    │   ├─ repo.get_allocation()       → pesi attuali
    │   ├─ repo.list_portfolio_target_allocations() → pesi target
    │   └─ repo.get_portfolio_target_performance()  → best/worst
    │   → formatta tutto in testo strutturato
    │
    ▼
SYSTEM_PROMPT.format(context=portfolio_text)
    │
    ▼
anthropic.messages.stream(system=..., messages=conversazione)
    │
    ▼
StreamingResponse (SSE text/event-stream)
    │
    ▼
Frontend legge ReadableStream, parsa chunk SSE,
appende text_delta all'ultimo messaggio assistant
```

---

## File da creare/modificare

### 1. NUOVO: `src/backend/app/advisor_service.py` (~120 righe)

File core dell'agente. Contiene:

**Modelli Pydantic:**
- `AdvisorMessage(role: Literal["user","assistant"], content: str)`
- `AdvisorChatRequest(portfolio_id: int, messages: list[AdvisorMessage])`

**`build_portfolio_context(repo, portfolio_id, user_id) → str`:**
- Chiama i metodi repository esistenti (summary, positions, allocation, target_allocations, target_performance)
- Formatta i dati in testo markdown strutturato con tabelle (posizioni, drift attuale vs target, best/worst performer)
- Tronca a max 30 posizioni per peso per evitare limiti token

**`SYSTEM_PROMPT` (costante):**
- Istruzioni in italiano per l'agente
- Ruolo: consulente finanziario AI per Valore365
- Capacità: analisi ribilanciamento, ottimizzazione target, analisi generale
- Regole: basarsi solo sui dati forniti, non inventare, specificare che sono suggerimenti non raccomandazioni personalizzate
- Placeholder `{context}` per i dati portfolio

**`stream_advisor_response(api_key, model, system_prompt, messages) → Generator`:**
- Usa `anthropic.Anthropic(api_key=...)` (client sync)
- `client.messages.stream(model=..., max_tokens=2048, system=..., messages=...)`
- Yield chunk SSE formattati: `data: {"type":"text_delta","content":"..."}\n\n`
- Yield finale: `data: {"type":"done","content":""}\n\n`
- Gestione errori con yield `data: {"type":"error","content":"..."}\n\n`

### 2. MODIFICA: `src/backend/app/config.py`

Aggiungere alla classe `Settings`:
```python
anthropic_api_key: str = ""
advisor_model: str = "claude-sonnet-4-20250514"
```
Letti da env vars `ANTHROPIC_API_KEY` e `ADVISOR_MODEL`.

### 3. MODIFICA: `src/backend/app/main.py`

Aggiungere 2 endpoint:

**`POST /api/advisor/chat`** → `StreamingResponse(media_type="text/event-stream")`
- Auth required
- Se `anthropic_api_key` vuoto → 503
- Chiama `build_portfolio_context` → `SYSTEM_PROMPT.format(context=...)` → `stream_advisor_response`
- Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`

**`GET /api/advisor/status`** → `{"available": bool}`
- Permette al frontend di sapere se l'advisor è configurato

### 4. MODIFICA: `src/backend/requirements.txt`

Aggiungere:
```
anthropic>=0.39.0
```

### 5. NUOVO: `src/frontend/valore-frontend/src/components/advisor/AdvisorChat.tsx` (~180 righe)

Componente chat sidebar:
- **Mantine `Drawer`** che si apre da destra, `size="lg"` (~550px)
- **Titolo**: icona sparkles + "AI Advisor"
- **Lista messaggi** in `ScrollArea` con auto-scroll
  - Messaggi utente: allineati a destra, sfondo blu
  - Messaggi assistant: allineati a sinistra, sfondo grigio, con rendering markdown base
- **Input** in basso: `TextInput` + `ActionIcon` invio (anche su Enter)
- **Suggerimenti rapidi** mostrati quando la chat è vuota:
  - "Analizza il ribilanciamento del mio portfolio"
  - "Come posso migliorare la diversificazione?"
  - "Qual è la mia esposizione attuale vs target?"
- **Streaming SSE**: `fetch` diretto (non `apiFetch`) con `ReadableStream` reader
- **Stato**: `messages[]`, `input`, `streaming`, `error` in React state
- **Reset** conversazione al cambio portfolio
- **AbortController** per cancellare richieste in corso alla chiusura

Props: `{ opened, onClose, portfolioId }`

### 6. NUOVO: `src/frontend/valore-frontend/src/components/advisor/MessageBubble.tsx` (~50 righe)

Sub-componente per singolo messaggio:
- `Paper` Mantine con stile condizionale per role
- Rendering testo con `whiteSpace: pre-wrap` per preservare formattazione
- Indicatore "typing" (3 puntini) quando streaming e contenuto vuoto

### 7. MODIFICA: `src/frontend/valore-frontend/src/services/api.ts`

Aggiungere:
- Tipi `AdvisorMessage`, `AdvisorStatus`
- `getAdvisorStatus(): Promise<AdvisorStatus>`
- `getAuthToken(): Promise<string | null>` — esporta il token getter per uso diretto in fetch SSE

### 8. MODIFICA: `src/frontend/valore-frontend/src/pages/Dashboard.page.tsx`

- Import `AdvisorChat` e `IconSparkles`
- Stato `advisorOpened` con `useDisclosure`
- Check `advisorAvailable` con `getAdvisorStatus` al mount
- **Bottone FAB** (floating action button) o `ActionIcon` gradient viola/cyan nell'header vicino al selettore portfolio
- Render `<AdvisorChat opened={advisorOpened} onClose={closeAdvisor} portfolioId={selectedPortfolioId} />`
- Bottone nascosto se advisor non disponibile

---

## Configurazione

Variabili d'ambiente da aggiungere (`.env`):
```
ANTHROPIC_API_KEY=sk-ant-...        # obbligatorio per attivare l'advisor
ADVISOR_MODEL=claude-sonnet-4-20250514  # opzionale, default sonnet
```

Se la API key non è configurata, il bottone advisor non appare nel frontend.

---

## Sicurezza Multi-tenant

- `build_portfolio_context` passa sempre `user_id` (da `require_auth`) a ogni metodo repository
- Ogni query SQL filtra per `owner_user_id` — l'agente vede solo dati dell'utente autenticato
- Nessun dato cross-user possibile

---

## Sequenza di implementazione

1. `requirements.txt` — aggiungere `anthropic`
2. `config.py` — aggiungere settings
3. `advisor_service.py` — creare file (modelli, context builder, prompt, streaming)
4. `main.py` — aggiungere 2 route
5. `api.ts` — aggiungere tipi e funzioni
6. `MessageBubble.tsx` — creare componente
7. `AdvisorChat.tsx` — creare componente chat
8. `Dashboard.page.tsx` — integrare bottone e drawer

**Codice nuovo totale stimato: ~400 righe**

---

## Verifica

1. **Backend**: avviare il server, testare `GET /api/advisor/status` → `{"available": true}`
2. **Backend**: testare `POST /api/advisor/chat` con curl e verificare streaming SSE
3. **Frontend**: verificare bottone advisor visibile nella dashboard
4. **Frontend**: aprire drawer, inviare messaggio, verificare risposta streaming
5. **E2E**: selezionare un portfolio con target allocation, chiedere analisi ribilanciamento, verificare che i dati citati corrispondano ai dati reali del portfolio
