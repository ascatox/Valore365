---
id: TASK-31
title: Hardening del server MCP
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T12:00:00Z'
labels:
  - mcp
  - security
milestone: m-0
dependencies:
  - TASK-30
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il server MCP in sola lettura (TASK-30) è protetto da OAuth Clerk, rate limit per utente e protezione DNS rebinding. Questo task aggiunge difese in profondità prima dell'apertura agli utenti: esposizione esplicita dei tool (fail closed), sola lettura rigorosa anche per l'X-Ray, protezioni contro l'abuso prima dell'autenticazione, verifica JWT più rigorosa, limiti per singola chiamata, validazione degli argomenti, riduzione della superficie di prompt injection, header di risposta sicuri, rilascio graduale con kill switch per utente e audit log strutturato. Include la verifica delle dipendenze con pip-audit.

Nota: l'esposizione automatica dei nuovi tool del Copilot descritta nel criterio #12 di TASK-30 è sostituita dall'allowlist esplicita `MCP_TOOL_ALLOWLIST`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 I tool MCP sono esposti solo se elencati in `MCP_TOOL_ALLOWLIST`; un nuovo tool del Copilot non compare su MCP finché non viene aggiunto, e un test fallisce se un tool di `TOOL_DEFINITIONS` non è né nell'allowlist né in `MCP_TOOL_EXCLUDED`
- [x] #2 `get_xray_summary` via MCP non riceve il client justETF e non scrive mai nella cache `etf_enrichment` (verificato da test)
- [x] #3 Dopo troppe autenticazioni fallite dallo stesso IP (`TRUSTED_PROXY_IPS` rispettato) `/mcp` risponde 429 prima di contattare Clerk o il JWKS; i token opachi rifiutati sono in cache negativa; a Clerk arrivano solo token `oat_` ben formati; header `Authorization` oltre 4096 caratteri rifiutati senza parsing; refetch del JWKS per `kid` sconosciuti al massimo ogni 30 s
- [x] #4 JWT: `alg` fissato a RS256 (rifiutati `none`/`HS*`/`crit`), `nbf` e `iat` futuri rifiutati con tolleranza 5 s, durata massima configurabile (`MCP_MAX_TOKEN_LIFETIME_SECONDS`), warning all'avvio se `MCP_REQUIRE_AUDIENCE=false`
- [x] #5 Limiti per chiamata: timeout per tool con errore generico, risultato limitato a 200 KB con marcatore di troncamento, massimo 4 chiamate in corso per utente, rate limit più stretto per i tool pesanti
- [x] #6 Argomenti validati contro uno schema JSON rigoroso prima dell'esecuzione (nessun argomento sconosciuto, `portfolio_id` intero positivo, numeri e stringhe limitati, NaN/Inf rifiutati); i batch JSON-RPC sono rifiutati
- [x] #7 Dagli output dei tool vengono rimossi caratteri di controllo, bidi, a larghezza zero e tag Unicode; descrizioni dei tool e istruzioni del server avvertono che gli output sono dati, non istruzioni
- [x] #8 Le risposte di `/mcp` hanno `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` e `X-Request-ID`; i `.well-known` restano cacheabili con `nosniff`; 401/403/429 hanno messaggi generici
- [x] #9 `MCP_ALLOWED_USER_IDS` e `MCP_BLOCKED_USER_IDS` (403) documentati in `docs/mcp.md`, `.env.example` e `render.yaml`
- [x] #10 Audit log per richiesta e per chiamata a tool (request id, utente, client, tool, esito, durata, IP), senza token né output; autenticazioni fallite a livello WARNING con la sola categoria del motivo
- [x] #11 pip-audit eseguito: advisory di `mcp==1.12.4` analizzate (mitigate o non applicabili alla configurazione stateless con DNS rebinding protection) e documentate; aggiornamenti consigliati per PyJWT, starlette/fastapi, cryptography, Jinja2, python-multipart riportati
- [x] #12 `docs/mcp.md` contiene la sezione "Hardening" con tutti i controlli, le nuove variabili e la nota sui limiti in memoria per processo (caveat multi-istanza e `TRUSTED_PROXY_IPS` su Render)
- [x] #13 Test per ogni punto in `src/backend/tests/integration/test_mcp_server.py`; la suite backend completa passa
<!-- AC:END -->
