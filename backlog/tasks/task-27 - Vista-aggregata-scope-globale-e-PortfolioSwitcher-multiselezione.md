---
id: TASK-27
title: 'Vista aggregata: scope globale e PortfolioSwitcher con multiselezione'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T10:00:00Z'
labels:
  - frontend
  - vista-aggregata
dependencies: [TASK-26]
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Uno scope di portafoglio condiviso da tutta l'app, al posto della selezione duplicata in ogni pagina: { mode: 'single', id } oppure { mode: 'aggregate', ids }, salvato in localStorage. Il PortfolioSwitcher permette di scegliere più portafogli con la stessa valuta base.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 PortfolioScopeContext con persistenza in localStorage (letture/scritture protette) e migrazione dalle chiavi esistenti (selectedPortfolioId, fireAggregatePortfolioIds)
- [ ] #2 PortfolioSwitcher: sezione Vista aggregata con multiselezione limitata alla stessa valuta base, badge Aggregato (N), funziona anche nel BottomSheet mobile
- [ ] #3 Hook in queries.ts guidati dallo scope: URL singolo o aggregate e query key che includono gli id ordinati
- [ ] #4 Se un portafoglio dello scope viene eliminato lo scope si ripulisce; con un solo portafoglio rimasto torna in modalità single
- [ ] #5 Test del context e dello switcher
<!-- AC:END -->
