
<!-- BACKLOG.MD MCP GUIDELINES START -->

<CRITICAL_INSTRUCTION>

## BACKLOG WORKFLOW INSTRUCTIONS

This project uses Backlog.md MCP for all task and project management activities.

**CRITICAL GUIDANCE**

- If your client supports MCP resources, read `backlog://workflow/overview` to understand when and how to use Backlog for this project.
- If your client only supports tools or the above request fails, call `backlog.get_workflow_overview()` tool to load the tool-oriented overview (it lists the matching guide tools).

- **First time working here?** Read the overview resource IMMEDIATELY to learn the workflow
- **Already familiar?** You should have the overview cached ("## Backlog.md Overview (MCP)")
- **When to read it**: BEFORE creating tasks, or when you're unsure whether to track work

These guides cover:
- Decision framework for when to create tasks
- Search-first workflow to avoid duplicates
- Links to detailed guides for task creation, execution, and finalization
- MCP tools reference

You MUST read the overview resource to understand the complete workflow. The information is NOT summarized here.

</CRITICAL_INSTRUCTION>

<!-- BACKLOG.MD MCP GUIDELINES END -->

## Server MCP (note per sviluppatori)

- Il server MCP remoto in sola lettura vive in `src/backend/app/mcp_server/` (`config.py`, `auth.py`, `tools.py`, `routes.py`) ed è registrato in `src/backend/app/main.py` su `/mcp`. Documentazione: `docs/mcp.md` (tecnica) e `docs/mcp-guida-utente.md` (utenti). Test: `src/backend/tests/integration/test_mcp_server.py`.
- I tool MCP devono restare **in sola lettura**: nessun tool che crea, modifica o cancella dati, nemmeno indirettamente (es. cache condivise su DB come `etf_enrichment`: per questo MCP non passa mai il client justETF a `execute_tool`). Non scrivere handler MCP separati: riusa `TOOL_DEFINITIONS` ed `execute_tool` di `src/backend/app/copilot_tools.py`.
- L'esposizione è **esplicita (fail closed)**: un nuovo tool del Copilot (voce in `TOOL_DEFINITIONS` + handler in `_TOOL_HANDLERS`) **non** compare su MCP finché non lo aggiungi a `MCP_TOOL_ALLOWLIST` in `app/mcp_server/tools.py`, dopo aver verificato che sia in sola lettura. Se non va esposto, aggiungilo a `MCP_TOOL_EXCLUDED` con il motivo. `test_every_copilot_tool_is_explicitly_allowlisted_or_excluded` fallisce finché non hai deciso.
- Ogni argomento di un tool esposto deve avere limiti in `ARGUMENT_CONSTRAINTS` (stringhe con `maxLength`, numeri con minimo e massimo; lo verifica `test_every_exposed_argument_is_bounded`); i tool costosi vanno aggiunti a `HEAVY_TOOLS`. Gli output passano da `sanitize_output`: non aggirarlo.
- Non loggare mai token, argomenti o output dei tool; i limiti (rate limit, concorrenza) sono in memoria per processo.
- `/mcp` non deve mai usare `require_auth` né il fallback `dev-user`: l'autenticazione passa solo da `app/mcp_server/auth.py` (access token OAuth di Clerk) e la configurazione è *fail closed*.
- Se aggiungi un tool, aggiorna la tabella dei tool in `docs/mcp.md` e, se utile, gli esempi in `docs/mcp-guida-utente.md`.
