---
id: TASK-4
title: 'Import CSV/XLSX: errore confronto datetime naive/aware in conferma'
status: Done
assignee: []
created_date: '2026-10-23 13:33'
updated_date: '2026-10-23 13:33'
labels:
  - backend
  - import
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In conferma dell'import, ogni riga falliva con "can't compare offset-naive and offset-aware datetimes": commit_batch creava trade_at senza fuso orario e il controllo di inventario ordinava la data insieme ai timestamptz già presenti nel DB.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 commit_batch salva trade_at con fuso orario (UTC)
- [x] #2 Il controllo di inventario confronta date naive e aware senza errori
- [x] #3 Test unitari per commit_batch e timeline inventario
<!-- AC:END -->
