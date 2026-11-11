---
id: TASK-80
title: 'Auditor: corsa notturna in produzione e storico degli esiti'
status: Done
assignee: []
created_date: '2026-11-10T18:00:00Z'
labels:
  - auditor
  - backend
  - database
  - ci
milestone: m-2
dependencies:
  - TASK-79
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
I portafogli di prova non hanno i casi strani dei dati reali: l'audit di novembre ha trovato i problemi più gravi proprio sui portafogli veri (import Fineco, XLSX, quotazioni in pence). L'Auditor deve girare anche in produzione, sul server, senza che i dati escano: un endpoint interno protetto da token, chiamato da un cron di GitHub Actions come la sincronizzazione dei prezzi, salva solo gli esiti.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un endpoint interno avvia la corsa su tutti i portafogli in background e uno di stato ne restituisce l'esito; autenticazione con token dedicato confrontato in tempo costante, endpoint disattivati se il token non è impostato, limiti di frequenza come in `routes_internal.py`
- [x] #2 Gli esiti vengono salvati per corsa, portafoglio e regola, solo con id regola, esito, severità e data: nessun importo, nome di strumento o testo di evidenza
- [x] #3 Una corsa in corso blocca l'avvio di un'altra; una corsa interrotta viene marcata come tale al riavvio
- [x] #4 Un workflow GitHub Actions avvia la corsa ogni notte dopo la sincronizzazione dei prezzi e fallisce se l'endpoint non risponde o la corsa termina in errore; il token passa solo dai secret
- [x] #5 Un endpoint amministrativo (con `require_admin`) restituisce l'ultima corsa: regole che falliscono, su quanti portafogli, da quando
- [x] #6 La corsa non consuma la quota MCP degli utenti e non rallenta le richieste: limiti di concorrenza e durata massima configurabili
- [x] #7 Migrazione in `database/migrations/` e `database/schema.sql`; test unitari e di integrazione coprono autenticazione, salvataggio senza dati personali, lock e corsa interrotta
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/api/routes_auditor_internal.py`, `src/backend/app/services/auditor/store.py`, la registrazione in `app/main.py`, le impostazioni in `app/config.py` e `.env.example`, la migrazione, `.github/workflows/auditor-production.yml`, i test relativi.
Riferimenti: `app/api/routes_internal.py`, `services/market_data_sync.py`, `.github/workflows/market-data-sync.yml`, `app/auth.py` (`require_admin`).
<!-- SECTION:NOTES:END -->
