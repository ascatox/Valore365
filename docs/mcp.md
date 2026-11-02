# Server MCP remoto (sola lettura)

> **Riferimento tecnico** per chi gestisce o sviluppa il server. Per collegare il proprio
> portafoglio a Claude o ChatGPT come utente finale, vedere la
> [guida utente](mcp-guida-utente.md).

Valore365 espone un server [Model Context Protocol](https://modelcontextprotocol.io) all'indirizzo
`https://valore365.onrender.com/mcp` (produzione; in locale `http://localhost:8000/mcp`). Permette a un assistente AI (Claude, ChatGPT, ecc.) di **leggere** i
portafogli dell'utente che ha fatto login con Clerk e di usare gli stessi strumenti di analisi del
Copilot interno (riepilogo, posizioni, performance, salute del portafoglio, X-Ray, stress test, ...).

- Trasporto: Streamable HTTP, modalità **stateless** con risposte JSON (nessuna sessione lato server).
- SDK: pacchetto ufficiale `mcp` (Python), versione `1.30.0` (ultima della serie 1.x; la 2.x cambia
  l'API lato server). Vedi [Dipendenze](#dipendenze-pip-audit-novembre-2026).
- Codice: `src/backend/app/mcp_server/` (`config.py`, `auth.py`, `tools.py`, `routes.py`).
- Test: `src/backend/tests/integration/test_mcp_server.py`.

## Modello di sicurezza

**Sola lettura.** Il server non espone alcun tool di scrittura: non crea, modifica o cancella
portafogli, transazioni o impostazioni. I tool riusano i gestori del Copilot
(`app/copilot_tools.py`), che leggono e calcolano soltanto, e sono annotati con
`readOnlyHint: true` e `destructiveHint: false`. Sono esposti solo i tool elencati esplicitamente in
`MCP_TOOL_ALLOWLIST` (`app/mcp_server/tools.py`). Anche `get_xray_summary` è in sola lettura: via MCP
non riceve il client justETF, quindi non scarica né salva nella cache condivisa `etf_enrichment` i
profili ETF mancanti (cosa che invece fanno la pagina X-Ray e il Copilot interno, solo quando
`JUSTETF_XRAY_AUTO_ENRICH_ENABLED` è attivo: di default solo con `APP_ENV=dev`). Usa i dati già presenti in cache e, per gli altri ETF, le top
holdings di Yahoo Finance (cache in memoria, nessuna scrittura).

**Solo OAuth Clerk, niente `dev-user`.** Ogni richiesta a `/mcp` richiede
`Authorization: Bearer <access token OAuth emesso da Clerk>`. L'endpoint non usa `require_auth` e quindi
non ha il fallback `dev-user` usato in sviluppo quando `CLERK_AUTH_ENABLED=false`. Se MCP è
abilitato ma Clerk no, o se manca una variabile obbligatoria, l'endpoint **non viene servito**
(risponde 503 e nei log compare un errore esplicito): il comportamento è *fail closed*.

**Verifica del token** (`app/mcp_server/auth.py`), allineata a quella degli SDK ufficiali di Clerk:

| Formato token | Come si riconosce | Verifica |
|---|---|---|
| JWT | header `typ: at+jwt` (RFC 9068) | firma tramite JWKS con `alg` fissato a RS256 (rifiutati `none`, `HS*` e l'header `crit`), `exp`/`iat`/`sub`/`iss` obbligatori, `nbf` verificato se presente, `iat` non nel futuro, tolleranza 5 s, durata `exp - iat` al massimo `MCP_MAX_TOKEN_LIFETIME_SECONDS`, `iss` = `CLERK_ISSUER`, claim `client_id` presente |
| Opaco | prefisso `oat_` (solo caratteri `A-Z a-z 0-9 _ -`, lunghezza limitata) | `POST https://api.clerk.com/v1/oauth_applications/access_tokens/verify` con la secret key; il token deve risultare non revocato e non scaduto. L'esito positivo resta in cache per `MCP_TOKEN_CACHE_SECONDS`, quello negativo per `MCP_NEGATIVE_TOKEN_CACHE_SECONDS` (chiave: SHA-256 del token) |

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
Cache-Control: no-store
WWW-Authenticate: Bearer resource_metadata="https://valore365.onrender.com/.well-known/oauth-protected-resource/mcp", error="invalid_token", error_description="The access token is invalid or expired"
```

Senza alcun token l'header contiene solo `resource_metadata`, ed è questo che avvia il flusso OAuth
nei client. Il messaggio è **identico** per ogni causa (scaduto, firma errata, issuer, client non
ammesso, ...): il motivo compare solo nei log, come categoria (`reason=expired`, ...).

**Isolamento dei dati.** Ogni tool (tranne `list_portfolios`) richiede `portfolio_id`. Prima di
eseguirlo si verifica che il portafoglio appartenga all'utente del token (`resolve_portfolio_scope`).
In caso contrario il tool restituisce l'errore `Portfolio non trovato`.

**Altre protezioni:**

- rate limit per utente (`MCP_RATE_LIMIT_REQUESTS` richieste ogni `MCP_RATE_LIMIT_WINDOW_SECONDS`
  secondi, altrimenti 429), con lo stesso limiter a finestra scorrevole di `rate_limit.py`;
- ogni richiesta e ogni chiamata a un tool finiscono nel log `valore365.mcp` (audit, vedi
  [Hardening](#hardening)). Il log non contiene né il token, né gli argomenti, né l'output;
- i campi di testo (nomi, descrizioni) vengono ripuliti dai caratteri di controllo e invisibili e
  troncati a 1000 caratteri; i valori NaN/Inf diventano `null`. Le istruzioni del server e la
  descrizione di ogni tool ricordano al modello che i testi restituiti sono dati, non istruzioni
  (riduce la superficie di prompt injection);
- limiti per chiamata (timeout, concorrenza, dimensione del risultato, rate limit dei tool pesanti) e
  protezioni pre-autenticazione: vedi [Hardening](#hardening);
- sono accettate solo richieste POST (GET e DELETE restituiscono 405) e il body è limitato a 1 MB
  (413: controllato su `Content-Length` da noi e sul body effettivamente ricevuto dall'SDK, anche
  per upload chunked);
- protezione DNS rebinding dell'SDK: l'header `Host` deve corrispondere a `MCP_RESOURCE_URL`, e le
  richieste da browser con `Origin` sono rifiutate (403) salvo le origini elencate in `MCP_ALLOWED_ORIGINS`;
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
| `MCP_TOKEN_CACHE_SECONDS` | no | `60` | Durata della cache delle verifiche positive dei token opachi |
| `MCP_NEGATIVE_TOKEN_CACHE_SECONDS` | no | `60` | Durata della cache dei token opachi rifiutati da Clerk |
| `MCP_AUTH_FAILURE_LIMIT` / `MCP_AUTH_FAILURE_WINDOW_SECONDS` | no | `20` / `300` | Autenticazioni fallite per IP prima del 429 (`0` = disattivato) |
| `MCP_MAX_TOKEN_LIFETIME_SECONDS` | no | `86400` | Durata massima di un JWT (`exp - iat`); `0` = nessun controllo |
| `MCP_TOOL_TIMEOUT_SECONDS` | no | `20` | Timeout di esecuzione di un tool |
| `MCP_MAX_CONCURRENT_CALLS_PER_USER` | no | `4` | Chiamate a tool in corso contemporaneamente per utente |
| `MCP_HEAVY_TOOL_RATE_LIMIT_REQUESTS` / `MCP_HEAVY_TOOL_RATE_LIMIT_WINDOW_SECONDS` | no | `10` / `60` | Rate limit per utente dei tool pesanti |
| `MCP_ALLOWED_USER_IDS` | no | vuoto (tutti) | Utenti Clerk (`user_...`) ammessi, separati da virgola: rilascio graduale |
| `MCP_BLOCKED_USER_IDS` | no | vuoto | Utenti Clerk bloccati (403), prevale su `MCP_ALLOWED_USER_IDS` |
| `TRUSTED_PROXY_IPS` | no | vuoto | IP dei proxy da cui fidarsi di `X-Forwarded-For` (già usata dall'Instant Analyzer) |

Le variabili sono elencate anche in `src/backend/.env.example` e in `render.yaml` (i segreti con
`sync: false`, da compilare nel dashboard di Render).

## Collegare i client (note per chi gestisce il server)

I passaggi per l'utente finale (claude.ai, Claude Desktop, Claude Code, ChatGPT), gli esempi di
domande, la revoca dell'accesso e la risoluzione dei problemi sono nella
[guida utente](mcp-guida-utente.md). Qui solo quello che serve lato server:

- **URL da comunicare agli utenti**: `MCP_RESOURCE_URL`, cioè `https://valore365.onrender.com/mcp`. In
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
curl -i -X POST https://valore365.onrender.com/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}'

# Metadata pubblici
curl https://valore365.onrender.com/.well-known/oauth-protected-resource
curl https://valore365.onrender.com/.well-known/oauth-authorization-server
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
401/403, audience e scope, metadata, isolamento dei portafogli, rate limit, solo POST, origini,
allowlist dei tool e tutti i controlli della sezione [Hardening](#hardening).

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
`execute_tool`, ma **solo** quelli elencati in `MCP_TOOL_ALLOWLIST` (`app/mcp_server/tools.py`):
l'esposizione è *fail closed*. Un tool aggiunto al Copilot **non** compare su MCP finché non viene
valutato. Per decidere:

1. verificare che il gestore sia in sola lettura (nessuna scrittura su DB, anche indiretta come la
   cache `etf_enrichment`) e che non richieda dipendenze che scrivono;
2. aggiungerlo a `MCP_TOOL_ALLOWLIST`, oppure a `MCP_TOOL_EXCLUDED` con il motivo;
3. se ha argomenti, definirne i limiti in `ARGUMENT_CONSTRAINTS` (stringhe con `maxLength`, numeri con
   minimo e massimo);
4. se è costoso (simulazioni, chiamate di rete), aggiungerlo a `HEAVY_TOOLS`;
5. aggiornare la tabella dei tool qui sopra.

I test fanno da guardia: `test_every_copilot_tool_is_explicitly_allowlisted_or_excluded` fallisce se
un tool di `TOOL_DEFINITIONS` non è né nell'allowlist né tra gli esclusi, e
`test_every_exposed_argument_is_bounded` fallisce se un argomento esposto non ha limiti.

## Hardening

Controlli aggiuntivi rispetto al modello di sicurezza di base. Tutti i limiti sono **in memoria e per
processo**: con più istanze (o più worker uvicorn) ogni processo ha i propri contatori, quindi i
limiti effettivi si moltiplicano per il numero di processi e un'istanza riavviata riparte da zero.
Per limiti globali servirebbe uno store condiviso (ad esempio Redis), oggi non presente.

| Controllo | Comportamento | Configurazione |
|---|---|---|
| Allowlist dei tool | Solo i tool in `MCP_TOOL_ALLOWLIST` sono esposti; un nuovo tool del Copilot resta escluso finché non viene aggiunto (test di guardia) | codice (`tools.py`) |
| X-Ray in sola lettura | `get_xray_summary` gira senza client justETF: nessuna scrittura su `etf_enrichment` | codice |
| Limite tentativi falliti per IP | Dopo N autenticazioni fallite (token presente ma non valido) dallo stesso IP, `/mcp` risponde 429 **prima** di contattare Clerk o il JWKS, anche a token validi. La richiesta senza token (avvio del flusso OAuth) non conta | `MCP_AUTH_FAILURE_LIMIT`, `MCP_AUTH_FAILURE_WINDOW_SECONDS` |
| IP del client | `X-Forwarded-For` è considerato solo se la connessione arriva da un IP in `TRUSTED_PROXY_IPS` (stessa logica dell'Instant Analyzer). **Su Render**, senza `TRUSTED_PROXY_IPS`, l'IP visto è quello del proxy di Render: il limite diventa condiviso tra tutti i client e un attaccante potrebbe bloccare le autenticazioni altrui per la durata della finestra. In quel caso configurare `TRUSTED_PROXY_IPS` oppure impostare `MCP_AUTH_FAILURE_LIMIT=0` | `TRUSTED_PROXY_IPS` |
| Cache negativa token opachi | Un token `oat_` rifiutato da Clerk viene ricordato (SHA-256) e non ritrasmesso a Clerk; gli errori 5xx/429 di Clerk non vengono messi in cache | `MCP_NEGATIVE_TOKEN_CACHE_SECONDS` |
| Formato dei token | Header `Authorization` oltre 4096 caratteri rifiutati senza parsing; a Clerk arrivano solo token `oat_` con charset `A-Z a-z 0-9 _ -` e lunghezza 12-260; i JWT devono essere tre segmenti base64url | codice (`auth.py`) |
| Refetch JWKS limitato | Un `kid` sconosciuto provoca al massimo un nuovo download del JWKS ogni 30 s; nel frattempo i `kid` sconosciuti ricevono 401 (o 503 se il JWKS non è mai stato scaricato) | codice |
| JWT rigorosi | `alg` = RS256 (rifiutati `none`/`HS*`), `crit` rifiutato, `nbf` e `iat` futuri rifiutati (tolleranza 5 s), durata massima del token. All'avvio un warning se `MCP_REQUIRE_AUDIENCE=false` | `MCP_MAX_TOKEN_LIFETIME_SECONDS`, `MCP_REQUIRE_AUDIENCE` |
| Timeout per tool | Il tool gira in un thread; oltre il timeout il client riceve un errore generico. Il thread non può essere interrotto e termina in background, ma continua a occupare uno slot di concorrenza dell'utente finché non finisce | `MCP_TOOL_TIMEOUT_SECONDS` |
| Concorrenza per utente | Massimo N chiamate a tool in corso per utente, poi errore "Troppe richieste in corso" | `MCP_MAX_CONCURRENT_CALLS_PER_USER` |
| Rate limit tool pesanti | `get_monte_carlo`, `get_stress_test`, `get_income_projection`, `get_xray_summary`, `calculate_rebalance_orders`, `calculate_what_if`, `calculate_pac_contribution` hanno un limite per utente più stretto, in aggiunta a quello generale | `MCP_HEAVY_TOOL_RATE_LIMIT_REQUESTS`, `MCP_HEAVY_TOOL_RATE_LIMIT_WINDOW_SECONDS` |
| Dimensione del risultato | Il JSON del risultato è limitato a 200 KB: oltre, il testo viene tagliato con il marcatore `[risultato troncato: superato il limite di 200 KB]` e `structuredContent` è omesso | codice |
| Validazione argomenti | Schema JSON rigoroso (`additionalProperties: false`, `portfolio_id` intero positivo, numeri con minimo/massimo, `symbol` max 32 caratteri con charset limitato, NaN/Inf rifiutati), verificato sia dall'SDK sia da `run_tool_sync` prima di eseguire il tool. I batch JSON-RPC (array) non sono accettati dal trasporto dell'SDK (400) | `ARGUMENT_CONSTRAINTS` |
| Prompt injection | Oltre al troncamento, da tutti i testi (chiavi comprese) vengono rimossi caratteri di controllo, controlli bidirezionali Unicode, caratteri a larghezza zero/invisibili e caratteri "tag" (U+E0000-U+E0FFF); `\n` e `\t` restano. Ogni descrizione di tool e le istruzioni del server avvertono che gli output sono dati, non istruzioni | codice |
| Header di risposta | Tutte le risposte di `/mcp` (anche 401/404/429 e quelle dell'SDK) hanno `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` e `X-Request-ID`. I documenti `.well-known` restano `Cache-Control: public, max-age=300` (pubblici, uguali per tutti, senza dati utente) con `nosniff` | codice |
| Errori generici | 401 con messaggio unico qualunque sia la causa; 403 `Access denied` per gli utenti bloccati e `Insufficient scope` per gli scope mancanti; 429 generico; un portafoglio inesistente o altrui restituisce sempre `Portfolio non trovato` | codice |
| Rilascio graduale / kill switch | `MCP_ALLOWED_USER_IDS` non vuoto: solo quegli utenti possono usare MCP (gli altri ricevono 403). `MCP_BLOCKED_USER_IDS`: utenti sempre bloccati (403), ha la precedenza. Per spegnere tutto: `MCP_ENABLED=false` (404) | `MCP_ALLOWED_USER_IDS`, `MCP_BLOCKED_USER_IDS` |
| Audit log | Una riga per richiesta (`mcp request rid=… ip=… method=… status=… outcome=… user=… client=… duration_ms=…`) e una per chiamata a tool (`mcp tool call rid=… user=… client=… ip=… tool=… outcome=… duration_ms=…`), con lo stesso `rid` restituito in `X-Request-ID`. Le autenticazioni fallite sono loggate a livello WARNING con la sola categoria (`mcp auth failed rid=… ip=… reason=expired`). Mai token, argomenti o output | logger `valore365.mcp` |

### Dipendenze (pip-audit, novembre 2026)

Le dipendenze vulnerabili segnalate da `pip-audit` sono state aggiornate (TASK-32):

| Pacchetto | Prima | Ora | Note |
|---|---|---|---|
| `mcp` | 1.12.4 | 1.30.0 | Resta sulla serie 1.x; richiede `pydantic>=2.11` |
| `fastapi` | 0.115.8 | 0.162.0 | Necessaria per `starlette` 1.x |
| `starlette` | 0.45.3 (transitiva) | 1.10.0 (fissata) | |
| `pydantic` / `pydantic-settings` | 2.10.6 / 2.7.1 | 2.14.2 / 2.16.2 | |
| `uvicorn[standard]` | 0.34.0 | 0.54.0 | |
| `sse-starlette` | 3.0.3 | 3.6.0 | Transitiva di `mcp`, fissata |
| `PyJWT` | 2.10.1 | 2.15.1 | |
| `cryptography` | 44.0.2 | 50.0.2 | |
| `Jinja2` | 3.1.4 | 3.1.6 | |
| `python-multipart` | 0.0.20 | 0.0.33 | |
| `jsonschema` | (transitiva) | 4.26.0 | Importata da `tools.py`, ora fissata |
| `pytest` (solo dev) | 8.3.5 | 9.2.0 | CVE-2025-71176 |

Le nuove versioni richiedono **Python 3.11-3.13** (`starlette`, `pydantic-settings`,
`python-multipart` e `sse-starlette` richiedono >= 3.11; `scipy==1.15.2` non ha wheel per 3.14).
Il `Dockerfile` usa `python:3.12-slim`.

Dopo l'aggiornamento `pip-audit` non segnala advisory note né sui pacchetti di `requirements.txt`
né sull'ambiente completo installato da `requirements-dev.txt` (escluso `justetf-scraping`,
installato da GitHub e non presente nel database delle advisory).

Effetti dell'aggiornamento sul server MCP:

- rimosso il filtro di log per il falso "Error in message router" (`anyio.ClosedResourceError`)
  della modalità stateless della 1.12.x: la 1.30 lo registra solo a livello DEBUG (test
  `test_stateless_request_logs_no_teardown_errors`);
- il limite di 1 MB sul body è passato all'SDK (`max_request_body_size`), che risponde 413 anche
  agli upload chunked senza `Content-Length` (prima: eccezione e 500);
- un `Origin` non ammesso riceve 403 invece di 400;
- i batch JSON-RPC continuano a essere rifiutati dall'SDK (400).

Advisory della vecchia `mcp==1.12.4`, ora corrette, e impatto che avevano sulla nostra
configurazione (per riferimento):

| Advisory | Corretta in | Impatto con la 1.12.4 |
|---|---|---|
| GHSA-9h52-p55h-vw2f (DNS rebinding non attivo di default) | 1.23.0 | Mitigata: `enable_dns_rebinding_protection=True` esplicito, `allowed_hosts` = host di `MCP_RESOURCE_URL`, origini vuote di default, e comunque ogni richiesta è autenticata |
| GHSA-jpw9-pfvf-9f58 (sessione non legata al principal) | 1.27.2 | Non applicabile: modalità stateless, nessun `Mcp-Session-Id`, autenticazione su ogni richiesta |
| GHSA-84m7-p3x7-pcfv (sessioni stateful mai liberate) | 1.30.0 | Non applicabile: stateless, un session manager per richiesta |
| GHSA-vj7q-gjh5-988w (trasporto WebSocket senza controllo Host/Origin) | 1.28.1 | Non applicabile: WebSocket non usato |
| GHSA-w4fh-qvv9-3v23 (bearer auth dell'SDK senza audience) | 1.30.0 | Non applicabile: l'autenticazione è nostra (`auth.py`) e verifica `aud` se presente; consigliato `MCP_REQUIRE_AUDIENCE=true` |
| GHSA-5h93-6whr-6q8j, GHSA-rwrf-2pqf-9j8j (lato client: redirect, `$ref` remoti) | 1.30.0 | Non applicabili: usiamo solo il lato server |

Per verificare di nuovo:

```bash
cd src/backend
pip install pip-audit
grep -v justetf requirements.txt > /tmp/req.txt && pip-audit -r /tmp/req.txt
```
