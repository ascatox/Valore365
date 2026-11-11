---
id: TASK-79
title: 'Auditor: esecuzione in CI sui portafogli di prova'
status: To Do
assignee: []
created_date: '2026-11-10T18:00:00Z'
labels:
  - auditor
  - ci
milestone: m-2
dependencies:
  - TASK-73
  - TASK-74
  - TASK-75
  - TASK-76
  - TASK-77
  - TASK-78
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Con motore, regole e portafogli di prova pronti, l'Auditor deve girare da solo: su ogni PR che tocca i calcoli e ogni notte, così una regressione come quelle di novembre blocca la PR invece di arrivare agli utenti.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un workflow GitHub Actions avvia Postgres, applica schema, migrazioni e seed dell'Auditor, esegue la CLI su tutti i portafogli di prova e pubblica il report Markdown nel riepilogo del job e il JSON come artefatto
- [ ] #2 Il workflow parte sulle PR che modificano `src/backend/**` o `database/**`, ogni notte, e a mano; fallisce se c'è almeno un `fail` o `error` di severità P0 o P1
- [ ] #3 Un test di integrazione su Postgres esegue l'Auditor sul seed e verifica che, sul codice attuale, nessuna regola fallisca e nessuna vada in `skip` dove il catalogo prevede che sia valutata
- [ ] #4 La documentazione del backend spiega come eseguire l'Auditor in locale e come leggere il report
- [ ] #5 Le regole che falliscono sul codice attuale perché trovano un difetto reale non vengono disattivate: si apre un task nel backlog con l'evidenza e la regola resta, marcata nel catalogo come difetto noto con il task collegato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `.github/workflows/auditor.yml`, `src/backend/tests/integration/test_auditor_postgres.py`, la sezione Auditor in `src/backend/README.md`, eventuali task nuovi in `backlog/tasks/`.
Riferimenti: `.github/workflows/backend-rest-e2e-smoke.yml` (avvio di DB e migrazioni), `scripts/e2e/doctor2_stack.sh`.
Integrazione: un solo agente, dopo TASK-73…78.
Aggiornamento dopo l'ondata 1 (TASK-73…78):
- I tool del Doctor (`read_doctor_metrics` e simili) usano un servizio di processo legato al `DATABASE_URL` dell'app, non al repository passato in `ToolDependencies`: in CI l'Auditor deve girare con `DATABASE_URL` puntato al database del seed. Un test che costruisce le dipendenze su un altro engine deve sostituire `app.services.doctor_policy.service._default_service`, come fa `tests/integration/test_auditor_seed_postgres.py`.
- B-PAC-SUM fallisce sul codice attuale (verificato da TASK-75): con nessuno strumento sottopesato `calculate_pac_contribution` restituisce distribuzione vuota ma `total_allocated` pari all'intero importo. Aprire il task e marcare la regola con `known_defect`.
- Comando suggerito da TASK-73: `cd src/backend && python -m app.services.auditor --user auditor-seed-user --mode ci --fail-on P1 --json-out auditor-report.json --md-out auditor-report.md`.
- Da verificare sui dati del seed i tre punti segnalati da TASK-77 (D-PERF-RECOMPUTE sugli stessi dati del servizio, D-AGG-PERFORMANCE-VALUE con saldo iniziale senza transazioni, D-SUMMARY-PERFORMANCE-VALUE e cambio nei giorni senza prezzo).
<!-- SECTION:NOTES:END -->
