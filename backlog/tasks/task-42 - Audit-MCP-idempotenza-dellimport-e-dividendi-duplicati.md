---
id: TASK-42
title: 'Audit MCP: idempotenza dell''import e dividendi duplicati'
status: Done
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T11:11:00Z'
labels:
  - audit-mcp
  - backend
  - dati
  - import
milestone: m-1
dependencies:
  - TASK-37
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
V365-009. Le transazioni non hanno id esterno, hash di provenienza né vincolo di unicità; commit_batch non è atomico (un doppio commit è possibile); un nuovo upload dello stesso file reinserisce le righe. get_recent_transactions non espone l'id. get_dividend_summary somma valute diverse senza FX.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 commit_batch è atomico (claim con status 'committing' e un'unica transazione DB)
- [x] #2 Le righe importate hanno import_batch_id e source_hash; l'anteprima avvisa dei duplicati
- [x] #3 Reimportare lo stesso file non duplica; due movimenti legittimamente identici restano importabili secondo la regola decisa
- [x] #4 get_recent_transactions espone l'id della transazione
- [x] #5 Audit in sola lettura dei duplicati esistenti, senza cancellazioni automatiche
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Query di verifica in sola lettura: backlog/docs/AUDIT_MCP_2026-11_QUERY_DATI.sql (in attesa dei risultati dal proprietario).

2026-11-03: Q6-Q8 analizzate. Confermato: 'Lista Titoli (2).xlsx' confermato 4 volte il 2026-10-23 (batch 31/34/35/36) -> dividendi e un acquisto EUN5 quadruplicati in Wealth. In attesa dell'elenco completo degli id 5790-5870 per il piano di correzione dei dati.

2026-11-03 decisione (proposta dall'assistente, approvata con 'procedi'): nessuna migrazione dello schema; il commit del batch è atomico e un batch non può essere confermato due volte; le righe già presenti nel portafoglio (stesso strumento, tipo, data, quantità, prezzo, commissioni, valuta) sono segnalate nell'anteprima ed escluse per default, con possibilità di includerle.

2026-11-03: PARTE B dello script di correzione eseguita dal proprietario con COMMIT. 21 righe duplicate eliminate in Wealth (backup in backup_tx_dup_import_20261103). Verifiche superate: dividendi 46 righe per 4.121,72 EUR (prima 64 righe, 6.876,59 EUR); EUN5.DE 242 quote.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Senza migrazione dello schema (decisione 2026-11-03), quindi i criteri 1-2 sono soddisfatti in forma equivalente: il batch viene rivendicato con un update condizionale pending->committed nella STESSA transazione DB degli inserimenti (nessuno stato 'committing'); al posto di import_batch_id/source_hash, l'anteprima marca le righe già presenti con duplicate_of e salva lo sha256 del file in preview_data. Commit ripetuto -> 409; errore a metà -> rollback completo. Righe già presenti escluse per default (include_duplicates / include_row_numbers per includerle), avviso 'file già importato', conteggi inseriti/saltati. get_recent_transactions espone l'id. UI: badge 'Già presente', interruttore per includerle, pulsante protetto dal doppio invio. Test: test_csv_import_dedup.py (18), test_api_behavior.py, CsvImportModal.test.tsx. Aperti: gli asset vengono creati fuori dalla transazione atomica; i 21 duplicati esistenti si correggono con la PARTE B dello script SQL; get_dividend_summary con valute miste (non rilevante per i dati attuali).
<!-- SECTION:FINAL_SUMMARY:END -->
