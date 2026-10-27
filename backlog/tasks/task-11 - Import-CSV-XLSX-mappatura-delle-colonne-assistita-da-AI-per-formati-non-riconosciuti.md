---
id: TASK-11
title: >-
  Import CSV/XLSX: mappatura delle colonne assistita da AI per formati non
  riconosciuti
status: Done
assignee:
  - '@claude'
created_date: '2026-10-27T20:27:00Z'
updated_date: '2026-10-27T20:54:00Z'
labels:
  - ai
  - import
  - backend
  - frontend
milestone: m-0
dependencies: []
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
L'import riconosce solo i formati per cui esiste un parser dedicato (`src/backend/app/services/csv_service.py`): ogni nuovo broker richiede codice nuovo, e i task 3 e 4 mostrano quanto l'import sia fragile. Un utente con l'export di un broker non supportato oggi riceve un errore e deve rifare il file a mano. Il modello può proporre la corrispondenza fra le colonne del file e i campi della transazione; l'importazione vera resta deterministica e passa dall'anteprima esistente con conferma, quindi un errore del modello non salva mai dati sbagliati. Fuori scope: l'import pubblico dell'Instant Analyzer.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Se le intestazioni non corrispondono a nessun formato noto e l'AI è disponibile, il sistema propone una mappatura colonne del file -> campi della transazione
- [x] #2 Al modello vengono inviate solo le intestazioni e al massimo 5 righe di esempio
- [x] #3 La mappatura proposta viene validata (campi obbligatori presenti, date e importi interpretabili) prima di essere applicata
- [x] #4 L'utente vede la mappatura proposta nell'anteprima, può correggerla, e nessuna transazione viene salvata senza la sua conferma
- [x] #5 Se l'AI non è configurata o fallisce, il comportamento attuale (errore con messaggio) resta invariato
- [x] #6 I formati già supportati (generico, Fineco) non passano dall'AI
- [x] #7 Test con provider simulato su almeno 2 formati di broker non supportati
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Backend models (app/models.py): CsvColumnMapping (strict, extra=forbid: trade_at, isin, side, quantity, price required; trade_currency, fees, name optional; date_format as enum of whitelisted patterns), CsvImportMappingInfo (source ai|user, mapping, columns) and an optional column_mapping on CsvImportPreviewResponse.
2. New app/services/csv_ai_mapping.py: Italian system prompt + propose_column_mapping(config, columns, sample_rows). Sends ONLY headers + max 5 sample rows (cells truncated), reuses call_provider_for_text (extended with backward-compatible max_tokens/timeout kwargs), extracts strict JSON and validates it with Pydantic (unknown target fields rejected). Never logs rows or raw model output.
3. csv_service.py: (a) read the file as a neutral table (own delimiter + header-row detection, independent of the broker profile so the Fineco default skip_rows cannot eat an unknown file); (b) deterministic _validate_column_mapping (columns exist in file, no column reused, required fields present, sample dates/amounts/ISIN/side/currency parseable); (c) _apply_column_mapping converts rows to the canonical keys the existing row loop already parses, so parsing/validation/preview/commit stay the existing deterministic code; (d) parse_and_validate: AI is tried only when the known-format load/required-columns check raises ValueError (generic/Fineco never reach it); if AI is not configured, fails, or its mapping does not validate, the original ValueError is re-raised unchanged; a user-supplied column_mapping skips detection and AI.
4. routes_csv.py: optional column_mapping form field (JSON) -> 400 on malformed; run the sync service in a threadpool so the LLM call does not block the event loop.
5. Frontend: types + uploadCsvImportPreview(columnMapping?); CsvImportModal keeps the File, shows the proposed mapping (CsvColumnMappingEditor with a Select per field + date format), lets the user correct it and re-run the preview (old batch cancelled), disables Importa while edits are unapplied; nothing is saved without the existing explicit commit click.
6. Tests (tests/unit/test_csv_service.py): mocked provider on 2 unsupported broker formats (CSV with preamble/semicolon + XLSX English/ISO), supported formats never call the provider, AI unavailable/failing/invalid-JSON/unknown-field/non-existent-column/unparseable-date -> original error unchanged, only headers + <=5 rows sent, user-corrected mapping skips the AI. Frontend vitest for the mapping UI.
7. Run backend unit suite, frontend lint/test (+ tsc compared against baseline, which already has pre-existing errors), re-read diff adversarially, then finalize the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design: the model only proposes; the proposal (strict Pydantic model CsvColumnMapping, extra=forbid, date_format restricted to a whitelist) is validated deterministically against the file (columns exist, no column reused, required fields present, sample dates/amounts/ISIN/currency readable, at least one readable buy/sell label) and then rewritten into the canonical keys the existing row loop in parse_and_validate already parses. Preview rows, pending batch and commit_batch are untouched, so nothing is saved before the explicit commit.
Trigger: AI is tried only when the known-format load or required-columns check raises ValueError (generic/Fineco never reach it). Any failure (no config, unsupported provider, provider error, bad JSON, unknown field/column, failed validation) re-raises the original ValueError unchanged; verified old-vs-new on 11 inputs (identical errors and identical previews for supported files).
The file is re-read with a neutral table reader (own delimiter and header-row detection) instead of the broker profile, otherwise the Fineco default (skip_rows=7) would discard the header of an unknown file.
User correction: preview endpoint accepts an optional column_mapping form field (JSON); with it the service skips detection and AI (source=user). The UI keeps the File, re-posts it with the corrected mapping, cancels the superseded pending batch and disables Importa while edits are not applied.
Shared code touched: call_provider_for_text got backward-compatible keyword args max_tokens (default 220) and timeout (default None); the preview route now runs the service in a threadpool because the LLM call is slow.
Buy/sell labels are translated by a fixed IT/EN table in code (not by the model); rows with other labels (dividends, deposits) are flagged invalid in the preview, as today.
Verification: backend tests/unit 308 passed, tests/integration 34 passed (baseline 251 + 32); frontend lint clean, vitest 42 passed (baseline 39), npm run build ok; tsc -p tsconfig.app.json has 116 pre-existing errors on the clean tree and the same 116 after the change (none in touched files). Mutation checks: removing the mapping validation fails 9 tests, trying the AI for every file fails 3, removing the dirty-mapping guard on the Importa button fails 2 frontend tests.
Not done / follow-ups: no real-browser or real-provider run (no DB/Clerk/keys in this environment); signed quantities (negative for sells, no side column) and a controvalore column are not mapped; existing INFO logs in _parse_italian_number and in the parse_and_validate row loop already print row values and the new path inherits them (suggest demoting to DEBUG); Gemini branch of call_provider_for_text still prepends the explain-specific acknowledgement turn.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Unrecognised CSV/XLSX exports now get an AI-proposed column mapping that the user reviews and can correct in the import preview. The model only proposes (headers + at most 5 truncated sample rows are sent); the proposal is validated deterministically and applied through the existing row parser, so previews, pending batches and commit are unchanged and nothing is saved without the explicit Importa click.

Backend: new app/services/csv_ai_mapping.py (prompt, strict JSON parsing), mapping validation/application in csv_service.py, optional column_mapping on the preview endpoint, CsvColumnMapping/CsvImportMappingInfo models, call_provider_for_text extended with max_tokens/timeout. Frontend: CsvColumnMappingEditor (a Select per field plus date format, re-runs the preview, cancels the superseded batch, blocks Importa while edits are unapplied) wired into CsvImportModal.

Verified: backend unit 308 passed and integration 34 passed; frontend lint clean, vitest 42 passed, build ok; tsc shows only the 116 errors that already exist on the clean tree. Tests use a mocked provider on two unsupported formats (Italian semicolon CSV with a preamble, English XLSX with native dates) and cover supported formats never calling the AI, every failure mode keeping the original error (compared with the old code), the 5-row limit, and the user-corrected mapping.

Risks/follow-ups: not run against a real provider or in a browser; signed quantities and controvalore are not mapped; server-key AI calls are bounded only by the existing 120 req/min per-user limit; existing INFO logs of row values should become DEBUG.
<!-- SECTION:FINAL_SUMMARY:END -->
