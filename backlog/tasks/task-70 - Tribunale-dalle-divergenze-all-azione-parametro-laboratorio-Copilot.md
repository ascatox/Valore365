---
id: TASK-70
title: 'Tribunale: dalle divergenze all''azione (parametro, laboratorio, Copilot)'
status: To Do
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - doctor
  - tribunale
  - frontend
  - copilot
milestone: m-0
dependencies:
  - TASK-69
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Una seduta che finisce con «le voci non concordano sulla concentrazione» lascia l'utente a metà. Le sezioni per decidere esistono già: I miei parametri per fissare una regola, il Laboratorio per provare un'alternativa, il Copilot per approfondire. Questo task collega ogni punto conteso a quelle sezioni, senza che il Tribunale salvi o modifichi nulla.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Da un punto conteso l'utente può chiedere al Copilot di approfondirlo: la chat si apre con una domanda precompilata che riporta il punto e i fatti citati
- [ ] #2 Da un punto conteso legato a una metrica del Doctor l'utente può aprire I miei parametri con una bozza di regola su quella metrica, da confermare con il flusso esistente; nulla viene salvato senza conferma
- [ ] #3 Da un punto conteso l'utente può aprire il Laboratorio per costruire uno scenario
- [ ] #4 Le azioni compaiono solo se la sezione di destinazione è attiva e, in vista aggregata, solo dove ha senso
- [ ] #5 Nessuna azione propone strumenti da comprare o vendere né precompila soglie non scelte dall'utente
- [ ] #6 Test coprono le tre azioni, le sezioni spente e la vista aggregata
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: i componenti delle azioni in `components/doctor/tribunal/` e i punti di aggancio in `Doctor.page.tsx` (dopo TASK-69, per non sovrapporsi).
Riferimenti: il passaggio di una bozza del Copilot all'editor manuale in `Doctor.page.tsx` (`setSection('parametri')`), `Doctor.alertPrompt.test.tsx` per l'apertura del Copilot con una domanda precompilata, `components/doctor/policy/PolicyDraftCard.tsx`.
<!-- SECTION:NOTES:END -->
