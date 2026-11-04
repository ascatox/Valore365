---
title: "Portfolio Doctor 2.0: Doctor Policy, Policy Evaluation, Copilot assistito e Scenario Lab"
status: "In Progress"
priority: "high"
created: 2026-11-04
labels: ["doctor", "backend", "frontend", "copilot", "feature"]
---

# Portfolio Doctor 2.0

## Contesto

PRD "Valore365 — Portfolio Doctor 2.0" v1.0 (4 novembre 2026). Il Doctor evolve da
Health Score standard a sistema personalizzabile e verificabile: policy personali per
scope (singolo portafoglio o vista aggregata), evaluation deterministica
PASS/FAIL/UNKNOWN con evidenze, Copilot che crea bozze e preview senza mai salvare,
laboratorio di simulazioni senza effetti sui dati reali.

Contratti: `docs/doctor2/api-contracts.md`. Architettura: `docs/doctor2/architecture.md`.
Metodologia: `docs/doctor2/financial-methodology.md`.

## Acceptance criteria

- [ ] Health Score standard invariato (test di regressione)
- [ ] Policy versionate, isolate per scope, optimistic locking (409), restore
- [ ] Evaluation 8 metriche MVP, PASS mai su dati UNKNOWN/stale, golden fixture PRD
- [ ] Copilot: bozze tipizzate, preview, conferma UI con token monouso; MCP read-only
- [ ] Scenario Lab: manuale, solo nuova liquidità, ribilanciamento; invarianti di capitale
- [ ] UI: Diagnosi / I miei parametri / Laboratorio, desktop + mobile, Privacy Mode
- [ ] Test unit/integration/sicurezza/E2E eseguiti e passati (`docs/doctor2/test-report.md`)
