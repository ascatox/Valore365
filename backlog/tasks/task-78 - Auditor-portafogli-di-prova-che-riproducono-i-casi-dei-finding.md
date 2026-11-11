---
id: TASK-78
title: 'Auditor: portafogli di prova che riproducono i casi dei finding'
status: Done
assignee: []
created_date: '2026-11-10T18:00:00Z'
labels:
  - auditor
  - database
  - test
milestone: m-2
dependencies:
  - TASK-72
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le regole servono a poco se i dati di prova non contengono i casi che hanno causato i finding. Serve un insieme di portafogli di prova, riproducibile e con prezzi deterministici, che esercita ogni regola: solo obbligazioni, oro tramite ETC, strumento quotato a Londra, dividendi in valute diverse, tentativo di import duplicato, vista aggregata, portafoglio vuoto, quotazioni ferme, target che richiedono vendite per finanziare acquisti.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Esiste uno script SQL di seed dell'Auditor, applicabile dopo schema e migrazioni, con date relative a `current_date` come `scripts/e2e/doctor2_seed.sql`
- [x] #2 Ogni regola del catalogo ha almeno un portafoglio di prova su cui viene valutata (non `skip`); il catalogo in `docs/auditor/rules.md` indica quale
- [x] #3 Prezzi e storico sono abbastanza lunghi da coprire le finestre degli stress test storici per almeno un portafoglio, e assenti per un altro (per esercitare il ramo proxy)
- [x] #4 Il seed non richiede rete: nessuna chiamata a Yahoo o justETF durante l'esecuzione; i TER e l'arricchimento necessari sono nel seed
- [x] #5 Un test di integrazione su Postgres applica schema, migrazioni e seed e verifica che i portafogli attesi esistano con i valori documentati
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `scripts/auditor/audit_seed.sql`, `scripts/auditor/README.md`, `src/backend/tests/integration/test_auditor_seed_postgres.py`.
Riferimenti: `scripts/e2e/doctor2_seed.sql`, `database/schema.sql`, `database/migrations/`, `tests/integration/conftest.py` (fixture `pg_engine`).
Parallelizzabile con TASK-73…77.
<!-- SECTION:NOTES:END -->
