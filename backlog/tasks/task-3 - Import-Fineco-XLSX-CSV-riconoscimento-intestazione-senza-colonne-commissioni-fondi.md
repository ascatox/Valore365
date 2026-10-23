---
id: TASK-3
title: >-
  Import Fineco XLSX/CSV: riconoscimento intestazione senza colonne commissioni
  fondi
status: Done
assignee: []
created_date: '2026-10-23 12:47'
updated_date: '2026-10-23 12:47'
labels:
  - backend
  - import
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
L'export Movimenti Dossier Titoli di Fineco può omettere le colonne commissioni fondi (sw/ingr/uscita, banca corrispondente, spese SGR). Il riconoscimento dell'intestazione richiedeva tutte le 15 colonne, quindi ripiegava su skip_rows=7 usando la prima riga dati come intestazione e falliva con 'Colonne obbligatorie mancanti'. Inoltre le celle numeriche Excel con 3 decimali venivano lette come migliaia.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Intestazione Fineco riconosciuta con le sole colonne obbligatorie (XLSX e CSV)
- [x] #2 Celle numeriche Excel con 3 decimali lette correttamente
- [x] #3 Test unitari per export ridotto e decimali
<!-- AC:END -->
