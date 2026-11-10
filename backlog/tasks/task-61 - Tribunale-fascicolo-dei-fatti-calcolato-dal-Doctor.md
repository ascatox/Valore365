---
id: TASK-61
title: 'Tribunale: fascicolo dei fatti calcolato dal Doctor'
status: To Do
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - doctor
  - tribunale
  - backend
milestone: m-0
dependencies:
  - TASK-60
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le tre voci del Tribunale possono citare solo dati calcolati dal Doctor. Serve un modulo che, dato uno scope (portafoglio singolo o vista aggregata), raccolga quei dati in un fascicolo di fatti con id stabili, già formattati in italiano. Il fascicolo è l'unica fonte di numeri della seduta: quello che non c'è non può essere detto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Dato uno scope, il modulo restituisce un fascicolo conforme allo schema di `docs/tribunale/api-contracts.md`, senza chiamare alcun LLM
- [ ] #2 Il fascicolo copre: metriche del registry del Doctor, health score con i suoi avvisi, costi (TER medio), concentrazione e X-Ray (prime esposizioni per paese e settore), stress test storici, percentili Monte Carlo, numero di posizioni e, se esiste una policy, le regole violate o non verificabili
- [ ] #3 Un dato mancante, stale o UNKNOWN compare come fatto non citabile con il motivo, mai come zero
- [ ] #4 A parità di dati di ingresso il fascicolo ha gli stessi id, lo stesso ordine e lo stesso hash; l'hash cambia quando cambia un valore
- [ ] #5 Funziona in vista aggregata e rifiuta scope non posseduti dall'utente con lo stesso errore del Doctor
- [ ] #6 I nomi degli strumenti sono troncati e ripuliti come nei tool del Copilot, e il fascicolo rispetta il limite di fatti del contratto dando priorità ai più rilevanti
- [ ] #7 Test unitari coprono portafoglio completo, dati mancanti, vista aggregata, stabilità dell'hash e portafoglio vuoto
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/services/tribunal/__init__.py`, `case_file.py`, `tests/unit/test_tribunal_case_file.py`. Non toccare altri file.
Riusare, senza duplicare calcoli: `services/doctor_policy/metrics.py` (`compute_metrics`, `format_it`), `services/doctor_policy/scope.py` e `service.py`, `services/portfolio_doctor/` (`_health`, `_xray`, `_stress`, `_monte_carlo`), `copilot_doctor_tools.py` per la sanitizzazione dei testi.
Parallelizzabile con TASK-62, 63, 64, 67.
Aggiornamento da TASK-60: per lo scope singolo chiamare prima `DoctorPolicyService.resolve_scope` (`resolve_doctor_scope` non verifica la proprietà). Se importare `clean_text` da `copilot_doctor_tools` crea un ciclo, importarlo dentro la funzione.
<!-- SECTION:NOTES:END -->
