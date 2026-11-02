# Server MCP remoto (sola lettura)

> **Riferimento tecnico** per chi gestisce o sviluppa il server. Per collegare il proprio
> portafoglio a Claude o ChatGPT come utente finale, vedere la
> [guida utente](mcp-guida-utente.md).

Valore365 espone un server [Model Context Protocol](https://modelcontextprotocol.io) all'indirizzo
`https://<host-backend>/mcp`. Permette a un assistente AI (Claude, ChatGPT, ecc.) di **leggere** i
portafogli dell'utente che ha fatto login con Clerk e di usare gli stessi strumenti di analisi del
Copilot interno (riepilogo, posizioni, performance, salute del portafoglio, X-Ray, stress test, ...).

- Trasporto: Streamable HTTP, modalità **stateless** con risposte JSON (nessuna sessione lato server).
- SDK: pacchetto ufficiale `mcp` (Python), versione `1.12.4` (l'ultima compatibile con
  `pydantic==2.10.6`; dalla 1.13 serve `pydantic>=2.11`).
- Codice: `src/backend/app/mcp_server/` (`config.py`, `auth.py`, `tools.py`, `routes.py`).
- Test: `src/backend/tests/integration/test_mcp_server.py`.

## Modello di sicurezza

**Sola lettura.** Il server non espone alcun tool di scrittura: non crea, modifica o cancella
portafogli, transazioni o impostazioni. I tool riusano i gestori del Copilot
(`app/copilot_tools.py`), che leggono e calcolano soltanto, e sono annotati con
`readOnlyHint: true` e `destructiveHint: false`. Unico effetto collaterale: come nella pagina X-Ray,
`get_xray_summary` può popolare la cache condivisa dei dati ETF (`etf_enrichment`), che contiene dati
di mercato e non dati dell'utente.

**Solo OAuth Clerk, niente `dev-user`.** Ogni richiesta a `/mcp` richiede
`Authorization: Bearer <access token OAuth emesso da Clerk>`. L'endpoint non usa `require_auth` e quindi
non ha il fallback `dev-user` usato in sviluppo quando `CLERK_AUTH_ENABLED=false`. Se MCP è
abilitato ma Clerk no, o se manca una variabile obbligatoria, l'endpoint **non viene servito**
(risponde 503 e nei log compare un errore esplicito): il comportamento è *fail closed*.

**Verifica del token** (`app/mcp_server/auth.py`), allineata a quella degli SDK ufficiali di Clerk:

| Formato token | Come si riconosce | Verifica |
|---|---|---|
| JWT | header `typ: at+jwt` (RFC 9068) | firma RS256 tramite JWKS, `exp`/`iat`/`sub`/`iss` obbligatori, `iss` = `CLERK_ISSUER`, claim `client_id` presente |
| Opaco | prefisso `oat_` | `POST https://api.clerk.com/v1/oauth_applications/access_tokens/verify` con la secret key; il token deve risultare non revocato e non scaduto. L'esito positivo resta in cache per `MCP_TOKEN_CACHE_SECONDS` (chiave: SHA-256 del token) |

Per entrambi i formati:

- il **session token** della web app (JWT con `typ: JWT`, firmato con le stesse chiavi) viene
  **rifiutato**: per MCP vale solo un access token OAuth;
- `sub` deve essere un utente Clerk (`user_...`). È l'unica identità usata per accedere ai dati;
- **audience**: se il token contiene `aud`, deve includere `MCP_RESOURCE_URL`. Con
  `MCP_REQUIRE_AUDIENCE=true` un token senza `aud` viene rifiutato;
- facoltativi: lista di client OAuth ammessi (`MCP_ALLOWED_CLIENT_IDS`) e scope obbligatori
  (`MCP_REQUIRED_SCOPES`, se mancano la risposta è 403 `insufficient_scope`).

Il token non compare mai nei log e non viene inoltrato ad altri servizi. Fa eccezione l'endpoint di
verifica di Clerk, usato solo per i token opachi.

**Risposte di errore** (MCP authorization spec 2025-06-18, RFC 6750 e RFC 9728):

```
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer resource_metadata="https://<host>/.well-known/oauth-protected-resource/mcp", error="invalid_token", error_description="Token expired"
```

Senza alcun token l'header contiene solo `resource_metadata`, ed è questo che avvia il flusso OAuth
nei client.

**Isolamento dei dati.** Ogni tool (tranne `list_portfolios`) richiede `portfolio_id`. Prima di
eseguirlo si verifica che il portafoglio appartenga all'utente del token (`resolve_portfolio_scope`).
In caso contrario il tool restituisce l'errore `Portfolio non trovato`.

**Altre protezioni:**

- rate limit per utente (`MCP_RATE_LIMIT_REQUESTS` richieste ogni `MCP_RATE_LIMIT_WINDOW_SECONDS`
  secondi, altrimenti 429), con lo stesso limiter a finestra scorrevole di `rate_limit.py`;
- ogni chiamata a un tool finisce nel log `valore365.mcp` con utente, client, nome del tool, esito e
  durata. Il log non contiene né il token né l'output;
- i campi di testo lunghi (nomi, descrizioni) vengono troncati a 1000 caratteri e i valori NaN/Inf
  diventano `null`. Le istruzioni del server ricordano al modello che i testi restituiti sono dati,
  non istruzioni (riduce la superficie di prompt injection);
- sono accettate solo richieste POST (GET e DELETE restituiscono 405) e il body è limitato a 1 MB;
- protezione DNS rebinding dell'SDK: l'header `Host` deve corrispondere a `MCP_RESOURCE_URL`, e le
  richieste da browser con `Origin` sono rifiutate salvo le origini elencate in `MCP_ALLOWED_ORIGINS`;
- **CORS invariato**: Claude e ChatGPT si collegano dai loro server (server-to-server), quindi il
  CORS non c'entra e la configurazione CORS del resto dell'API resta com'è.

## Endpoint pubblicati

Gli endpoint esistono solo se MCP è abilitato e configurato correttamente. Altrimenti rispondono
404 (MCP disabilitato) o 503 (configurazione non valida).

| Metodo e path | Autenticazione | Descrizione |
|---|---|---|
| `POST /mcp` | Bearer OAuth | Endpoint MCP (JSON-RPC: `initialize`, `tools/list`, `tools/call`, `ping`) |
| `GET /.well-known/oauth-protected-resource` e `.../oauth-protected-resource/mcp` | pubblico | Protected Resource Metadata (RFC 9728) |
| `GET /.well-known/oauth-authorization-server` e `.../oauth-authorization-server/mcp` | pubblico | Copia (in cache per 1 ora) dei metadata OAuth di Clerk (`<CLERK_ISSUER>/.well-known/oauth-authorization-server`), per i client che seguono la spec MCP 2025-03-26 |

Esempio di Protected Resource Metadata:

```json
{
  "resource": "https://valore365.onrender.com/mcp",
  "authorization_servers": ["https://clerk.example.com"],
  "bearer_methods_supported": ["header"],
  "scopes_supported": ["profile", "email"],
  "resource_name": "Valore365"
}
```

## Tool disponibili

| Tool | Parametri |
|---|---|
| `list_portfolios` | nessuno: restituisce id, nome e valuta base dei portafogli dell'utente |
| `get_portfolio_summary`, `get_positions`, `get_target_drift`, `get_performance`, `get_cash_balance`, `get_recent_transactions`, `get_portfolio_health`, `get_day_movers`, `get_monte_carlo`, `get_dividend_summary`, `get_cost_breakdown`, `get_xray_summary`, `get_stress_test`, `get_income_projection` | `portfolio_id` |
| `calculate_rebalance_orders` | `portfolio_id`, `available_cash` (opzionale) |
| `calculate_what_if` | `portfolio_id`, `action` (`buy`/`sell`), `symbol`, `amount_eur` |
| `calculate_pac_contribution` | `portfolio_id`, `monthly_amount` |
| `search_asset_info` | `portfolio_id`, `symbol` |

I tool `calculate_*` sono **simulazioni**: calcolano ordini o pesi ipotetici ma non registrano nulla.

## Configurazione del dashboard Clerk

> Le voci del dashboard Clerk cambiano nel tempo: se un nome non corrisponde, cercare la sezione
> "OAuth applications" nella documentazione di Clerk ("Build an MCP server").

1. **Abilitare le OAuth applications** (Clerk come authorization server OAuth 2.1 / OIDC):
   Dashboard → *Configure* → *OAuth applications*.
2. **Abilitare la Dynamic Client Registration** nelle impostazioni delle OAuth applications. Claude e
   ChatGPT registrano da soli il proprio client (RFC 7591). Senza DCR occorre creare a mano
   un'OAuth application per ciascun client, inserire come redirect URI quello del client (per
   claude.ai `https://claude.ai/api/mcp/auth_callback`; per gli altri client, quello indicato nella
   loro documentazione) e passare client id e secret nelle impostazioni avanzate del connettore.
3. **Formato dell'access token**: sono supportati entrambi i formati.
   - **JWT** (consigliato): verifica locale tramite JWKS, nessuna chiamata a Clerk per ogni richiesta.
     `CLERK_SECRET_KEY` non serve.
   - **Opaco** (`oat_...`): serve `CLERK_SECRET_KEY`, perché ogni token nuovo viene verificato
     con la Backend API di Clerk. Senza la chiave i token opachi vengono rifiutati.
4. **Scope**: Clerk supporta `profile`, `email` (e `openid`). Il server pubblica `profile email` in
   `scopes_supported` e, salvo diversa configurazione (`MCP_REQUIRED_SCOPES`), non ne richiede di
   specifici: il server MCP usa solo l'id utente (`sub`).
5. **Frontend API URL** = `CLERK_ISSUER`. Si trova nel dashboard (*API keys* / *Domains*). In
   sviluppo ha la forma `https://<nome>.clerk.accounts.dev`, cioè lo stesso host di
   `CLERK_JWKS_URL` senza `/.well-known/jwks.json`. In produzione di solito è
   `https://clerk.<dominio>`.
6. **Audience**: se Clerk include `aud` negli access token (resource indicator RFC 8707 inviato dal
   client), il valore deve essere `MCP_RESOURCE_URL`. Dopo il primo collegamento conviene decodificare
   un token (ad esempio su jwt.io, senza condividerlo) per controllare `typ`, `iss`, `aud`,
   `client_id` e `scp`. Se `aud` è sempre presente e corretto, attivare `MCP_REQUIRE_AUDIENCE=true`.

## Variabili d'ambiente (backend)

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `MCP_ENABLED` | sì | `false` | Abilita `/mcp` e i documenti `.well-known` |
| `CLERK_AUTH_ENABLED` | sì | `false` | Deve valere `true`: senza Clerk MCP non viene servito |
| `MCP_RESOURCE_URL` | sì | — | URL pubblico dell'endpoint, es. `https://valore365.onrender.com/mcp` (https; http solo per localhost). È anche l'audience attesa e l'host accettato |
| `CLERK_ISSUER` | sì | — | Frontend API URL di Clerk (authorization server e `iss` atteso) |
| `CLERK_JWKS_URL` | no | `<CLERK_ISSUER>/.well-known/jwks.json` | JWKS già usato dall'API (stessa istanza Clerk) |
| `CLERK_SECRET_KEY` | solo con token opachi | — | Secret key Clerk (`sk_...`), per verificare i token `oat_` |
| `CLERK_API_URL` | no | `https://api.clerk.com/v1` | Backend API di Clerk |
| `MCP_ALLOWED_CLIENT_IDS` | no | vuoto (tutti) | Client OAuth ammessi, separati da virgola |
| `MCP_SCOPES_SUPPORTED` | no | `profile email` | Scope pubblicati nei metadata |
| `MCP_REQUIRED_SCOPES` | no | vuoto | Scope che il token deve avere |
| `MCP_REQUIRE_AUDIENCE` | no | `false` | Rifiuta i token senza `aud` |
| `MCP_ALLOWED_ORIGINS` | no | vuoto | Origini browser ammesse (es. MCP Inspector in locale) |
| `MCP_RATE_LIMIT_REQUESTS` / `MCP_RATE_LIMIT_WINDOW_SECONDS` | no | `60` / `60` | Rate limit per utente |
| `MCP_TOKEN_CACHE_SECONDS` | no | `60` | Durata della cache delle verifiche dei token opachi |

Le variabili sono elencate anche in `src/backend/.env.example` e in `render.yaml` (i segreti con
`sync: false`, da compilare nel dashboard di Render).

## Collegare i client (note per chi gestisce il server)

I passaggi per l'utente finale (claude.ai, Claude Desktop, Claude Code, ChatGPT), gli esempi di
domande, la revoca dell'accesso e la risoluzione dei problemi sono nella
[guida utente](mcp-guida-utente.md). Qui solo quello che serve lato server:

- **URL da comunicare agli utenti**: `MCP_RESOURCE_URL`, cioè `https://<host-backend>/mcp`. In
  produzione è l'host del backend su Render, non quello del frontend su Vercel (il rewrite di
  `vercel.json` copre solo `/api/*`). Nell'app lo mostra *Impostazioni → Copilot → "Collega Claude
  o ChatGPT (MCP)"*, ricavandolo da `VITE_API_BASE_URL` (origine + `/mcp`); se il frontend usa il
  valore relativo `/api`, l'URL mostrato è l'origine del frontend + `/mcp`, che funziona solo se
  quell'origine inoltra anche `/mcp` al backend. In quel caso impostare `VITE_MCP_SERVER_URL`.
- **DCR**: con la Dynamic Client Registration attiva in Clerk, claude.ai, Claude Code, ChatGPT e
  MCP Inspector si registrano da soli e i campi OAuth avanzati dei connettori restano vuoti. Senza
  DCR occorre creare a mano un'OAuth application per ciascun client (redirect URI di claude.ai:
  `https://claude.ai/api/mcp/auth_callback`) e comunicare client id e secret agli utenti.
- **Claude Team/Enterprise**: i connettori personalizzati li aggiunge un amministratore
  dell'organizzazione Claude; ogni utente poi fa *Connect* con il proprio login.
- **Claude Desktop** usa i connettori remoti di claude.ai (*Settings → Connectors*), non
  `claude_desktop_config.json`.
- **ChatGPT** richiede la *Developer mode* (*Settings → Apps & Connectors → Advanced settings*) e
  autenticazione OAuth; la disponibilità dipende dal piano e i nomi dei menu cambiano spesso.
- `MCP_ALLOWED_CLIENT_IDS` permette di limitare i client ammessi dopo averne osservato i
  `client_id` nei log (`valore365.mcp`).

## Verifica rapida (produzione)

```bash
# Senza token: 401 con WWW-Authenticate e resource_metadata
curl -i -X POST https://<host-backend>/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}'

# Metadata pubblici
curl https://<host-backend>/.well-known/oauth-protected-resource
curl https://<host-backend>/.well-known/oauth-authorization-server
```

Risposte attese: `401` con header `WWW-Authenticate: Bearer resource_metadata="..."` per la prima,
JSON con `resource` = `MCP_RESOURCE_URL` per la seconda, metadata OAuth di Clerk per la terza. Un
`404` vuol dire `MCP_ENABLED=false`; un `503` vuol dire configurazione incompleta (il motivo è nei
log all'avvio).

## Sviluppo e test in locale

### Test automatici

Da `src/backend`:

```bash
pytest tests/integration/test_mcp_server.py
```

I test non usano Clerk né il database: firmano JWT con una chiave RSA generata al volo (JWKS
finto), simulano la verifica dei token opachi e usano un repository fittizio. Coprono fail closed,
401/403, audience e scope, metadata, isolamento dei portafogli, rate limit, solo POST, origini e
corrispondenza tra tool MCP e `TOOL_DEFINITIONS`.

### Server locale con un'istanza Clerk di sviluppo

Il server MCP non ha modalità "senza login": anche in locale servono Clerk e le OAuth applications
(punti 1-2 della [configurazione del dashboard Clerk](#configurazione-del-dashboard-clerk)). In
`src/backend/.env`:

```env
CLERK_AUTH_ENABLED=true
CLERK_JWKS_URL=https://<nome>.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://<nome>.clerk.accounts.dev
MCP_ENABLED=true
MCP_RESOURCE_URL=http://localhost:8000/mcp
# solo per MCP Inspector (vedi sotto), da togliere dopo il test
MCP_ALLOWED_ORIGINS=http://localhost:6274
```

Poi `uvicorn app.main:app --reload --port 8000`. Con `CLERK_AUTH_ENABLED=true` anche le API `/api`
richiedono il login: il frontend locale va configurato con `VITE_CLERK_PUBLISHABLE_KEY` della stessa
istanza.

`MCP_RESOURCE_URL` deve corrispondere all'host usato dal client (protezione DNS rebinding): con
`http://localhost:8000/mcp` vanno usati `localhost:8000`, non `127.0.0.1:8000`.

### MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Nell'interfaccia (di default `http://localhost:6274`): trasporto **Streamable HTTP**, URL
`http://localhost:8000/mcp`, poi il flusso OAuth (*Open Auth Settings* / *Quick OAuth Flow* a
seconda della versione), login Clerk, *Connect*. Da *Tools* → *List Tools* compaiono
`list_portfolios` e i tool del Copilot; chiamare `list_portfolios` e poi un tool con un
`portfolio_id` restituito. Se l'Inspector si collega direttamente dal browser, la sua origine deve
essere in `MCP_ALLOWED_ORIGINS`, altrimenti la richiesta viene rifiutata.

### curl

```bash
# 401 + WWW-Authenticate
curl -i -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}'

# Con un access token OAuth valido (ad es. quello ottenuto dall'Inspector; mai un session token
# della web app, che viene rifiutato): elenco dei tool e chiamata
TOKEN='<access token OAuth>'
curl -s -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

curl -s -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_portfolios","arguments":{}}}'
```

Il server è stateless: non serve una richiesta `initialize` preliminare né l'header
`Mcp-Session-Id`.

### Claude Code in locale

Claude Code gira sulla macchina dello sviluppatore, quindi raggiunge `localhost`:

```bash
claude mcp add --transport http valore365-dev http://localhost:8000/mcp
```

claude.ai e ChatGPT invece si collegano dai propri server: per provarli serve un URL https pubblico
(ad esempio un tunnel) e `MCP_RESOURCE_URL` deve essere quell'URL.

## Aggiungere o modificare un tool

I tool MCP sono generati da `TOOL_DEFINITIONS` di `app/copilot_tools.py` ed eseguiti con
`execute_tool`: un tool aggiunto al Copilot (definizione in `TOOL_DEFINITIONS` + handler in
`_TOOL_HANDLERS`) compare automaticamente anche su MCP, con `portfolio_id` obbligatorio e
annotazione `readOnlyHint: true`. Non c'è una lista di esclusione: **ogni tool del Copilot deve
quindi restare in sola lettura**. Un tool che scrive richiederebbe prima un filtro esplicito in
`app/mcp_server/tools.py`. Dopo la modifica, `test_initialize_and_list_read_only_tools` verifica che
l'elenco MCP coincida con `TOOL_DEFINITIONS` + `list_portfolios`.
