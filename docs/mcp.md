# Server MCP remoto (sola lettura)

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
  "resource": "https://valore365-api.onrender.com/mcp",
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
| `MCP_RESOURCE_URL` | sì | — | URL pubblico dell'endpoint, es. `https://valore365-api.onrender.com/mcp` (https; http solo per localhost). È anche l'audience attesa e l'host accettato |
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

## Collegare Claude

URL del server: `https://<host-backend>/mcp` (lo stesso valore di `MCP_RESOURCE_URL`).

- **claude.ai** (web): *Settings* → *Connectors* → *Add custom connector*. Inserire nome
  (`Valore365`) e URL, poi *Connect*: si apre il login Clerk e, dopo il consenso, Claude riceve
  l'access token. Con la DCR attiva i campi OAuth avanzati restano vuoti. Nei piani Team/Enterprise
  i connettori personalizzati li aggiunge un amministratore.
- **Claude Desktop**: i connettori remoti si aggiungono dalla stessa voce *Settings* → *Connectors*
  (non da `claude_desktop_config.json`) e sono condivisi con claude.ai.
- **Claude Code**:

  ```bash
  claude mcp add --transport http valore365 https://<host-backend>/mcp
  ```

  Poi, dentro Claude Code, eseguire `/mcp`, selezionare `valore365` e completare il login nel browser.

## Collegare ChatGPT

In ChatGPT (piani che supportano i connettori personalizzati): *Settings* → *Apps & Connectors* →
*Advanced settings* → attivare **Developer mode**, poi *Create* (nuovo connettore/app). Inserire nome,
URL `https://<host-backend>/mcp` e autenticazione **OAuth**. ChatGPT legge i metadata, si registra su
Clerk via DCR e apre il login. In chat, attivare il connettore dal menu degli strumenti. I nomi esatti
dei menu cambiano spesso: fa fede la documentazione OpenAI su "developer mode" e "connectors".

## Esempi di prompt

- «Quali portafogli ho su Valore365?»
- «Dammi il riepilogo del portafoglio *Principale*: valore, P&L e variazione di oggi.»
- «Quali sono le 5 posizioni più pesanti e quanto pesano?»
- «Com'è andata la performance YTD e a 1 anno?»
- «Il portafoglio è in linea con il target? Se no, quali ordini servirebbero per ribilanciare con 2.000 € di liquidità?»
- «Cosa succederebbe ai pesi se comprassi 1.000 € di VWCE.DE?»
- «Fammi l'X-Ray: esposizione geografica e settoriale e i primi titoli sottostanti.»
- «Quanto pago di TER in totale e quanto mi costerà in 10 anni?»
- «Simula uno stress test e la proiezione Monte Carlo a 10 anni.»

## Verifica rapida

```bash
# Senza token: 401 con WWW-Authenticate e resource_metadata
curl -i -X POST https://<host-backend>/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}'

# Metadata pubblici
curl https://<host-backend>/.well-known/oauth-protected-resource
```

Per un test completo con OAuth usare [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
(`npx @modelcontextprotocol/inspector`), trasporto "Streamable HTTP". L'Inspector gira nel browser,
quindi la sua origine (es. `http://localhost:6274`) va aggiunta a `MCP_ALLOWED_ORIGINS` solo per il
tempo del test.
