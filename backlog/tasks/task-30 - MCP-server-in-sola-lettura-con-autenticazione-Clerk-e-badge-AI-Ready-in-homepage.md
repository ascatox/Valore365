---
id: TASK-30
title: MCP server in sola lettura con autenticazione Clerk e badge AI Ready in homepage
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T10:00:00Z'
labels:
  - mcp
  - security
  - ai
  - backend
  - frontend
milestone: m-0
dependencies: []
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Oggi i dati dei portafogli sono interrogabili solo dal Copilot interno. Esporre un server MCP remoto (`/mcp`, trasporto Streamable HTTP) che riusa i tool in sola lettura del Copilot (`copilot_tools.py`) permette a client esterni come Claude e ChatGPT di leggere i portafogli dell'utente in modo sicuro.

L'autenticazione avviene tramite OAuth con Clerk ed è fail-closed: senza token valido l'accesso è negato e non esiste mai un fallback all'utente di sviluppo. Il server verifica audience e issuer del token, pubblica i Protected Resource Metadata (RFC 9728) e applica un rate limit per utente. Non vengono esposti tool di scrittura.

Per comunicare la funzionalità, la landing page e il README mostrano un badge "AI Ready".
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Le richieste a `/mcp` senza token (o con token non valido, audience/issuer errati) ricevono 401 con header `WWW-Authenticate` che punta ai Protected Resource Metadata
- [ ] #2 Se Clerk è disabilitato l'endpoint `/mcp` non viene servito e non esiste alcun fallback all'utente di sviluppo
- [ ] #3 Il server espone solo i tool in sola lettura del Copilot più `list_portfolios`; nessun tool di scrittura è disponibile
- [ ] #4 Ogni tool verifica che il portafoglio richiesto appartenga all'utente autenticato; un portafoglio altrui restituisce errore senza dati
- [ ] #5 Il rate limit per utente è applicato e superata la soglia le richieste vengono rifiutate
- [ ] #6 I test backend esistenti e i nuovi test per il server MCP passano
- [ ] #7 `docs/mcp.md` descrive la configurazione di Clerk e come collegare Claude e ChatGPT al server
- [ ] #8 Il badge "AI Ready" è visibile nella homepage sia su desktop sia su mobile e nel README
<!-- AC:END -->
