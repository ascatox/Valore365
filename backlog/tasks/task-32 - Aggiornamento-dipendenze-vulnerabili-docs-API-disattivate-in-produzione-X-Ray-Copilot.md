---
id: TASK-32
title: 'Aggiornamento dipendenze vulnerabili, docs API disattivate in produzione, X-Ray Copilot'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T15:00:00Z'
labels:
  - security
  - backend
milestone: m-0
dependencies:
  - TASK-31
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seguito di TASK-31. Tre interventi di sicurezza sul backend:

1. Aggiornamento delle dipendenze segnalate da pip-audit (`mcp` 1.12.4 -> 1.30.0, restando sulla serie 1.x; `fastapi`/`starlette` 1.x; `PyJWT`; `cryptography`; `Jinja2`; `python-multipart`; `pydantic`/`pydantic-settings`/`uvicorn`/`sse-starlette` per compatibilità; `jsonschema` fissata perché importata da `app/mcp_server`), con adeguamento del codice e dei test e rimozione dei workaround legati al vecchio SDK MCP.
2. Le docs interattive FastAPI (`/docs`, `/redoc`) e `/openapi.json` non sono più pubbliche in produzione: nuova impostazione `API_DOCS_ENABLED` (default: attiva tranne con `APP_ENV=prod`).
3. Il Copilot interno rispetta `JUSTETF_XRAY_AUTO_ENRICH_ENABLED` come la pagina X-Ray: con l'arricchimento automatico disattivato `get_xray_summary` non scrive nella cache condivisa `etf_enrichment`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `requirements.txt` fissa versioni senza advisory note: `mcp==1.30.0`, `fastapi==0.162.0`, `starlette==1.10.0`, `PyJWT==2.15.1`, `cryptography==50.0.2`, `Jinja2==3.1.6`, `python-multipart==0.0.33`, `pydantic==2.14.2`, `pydantic-settings==2.16.2`, `uvicorn[standard]==0.54.0`, `sse-starlette==3.6.0`, `jsonschema==4.26.0`; commenti sui vecchi vincoli aggiornati
- [x] #2 `pip-audit` sui requisiti aggiornati e sull'ambiente dev completo non segnala advisory (anche `pytest` aggiornato a 9.2.0 in `requirements-dev.txt`)
- [x] #3 Server MCP: rimosso il filtro di log per il falso `ClosedResourceError` della 1.12.x (test che verifica l'assenza di errori nei log), limite del body delegato anche all'SDK (`max_request_body_size`, 413 anche per upload chunked), test aggiornati per `Origin` non ammesso (403); tutti i test di hardening restano verdi
- [x] #4 Test adeguati alle nuove versioni senza indebolirli (route annidate di FastAPI percorse con `iter_route_contexts`, chiave HMAC di test da 32 byte)
- [x] #5 `API_DOCS_ENABLED` (default `true` tranne con `APP_ENV=prod`/`production`) disattiva `/docs`, `/redoc` e `/openapi.json` (404); test per entrambe le modalità; il frontend non dipende da `/openapi.json`
- [x] #6 Il Copilot passa il client justETF agli strumenti solo se `justetf_xray_auto_enrich_enabled_resolved` è vero (stessa logica delle route X-Ray, default `None` = attivo solo in `dev`); test per i quattro casi
- [x] #7 Documentazione aggiornata: `docs/mcp.md` (dipendenze, pip-audit, comportamento 403/413), `src/backend/README.md` (`API_DOCS_ENABLED`, `JUSTETF_XRAY_AUTO_ENRICH_ENABLED`, Python 3.11-3.13), `render.yaml`
- [x] #8 La suite backend completa passa
<!-- AC:END -->
