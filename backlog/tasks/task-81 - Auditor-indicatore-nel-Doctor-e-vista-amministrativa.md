---
id: TASK-81
title: 'Auditor: indicatore nel Doctor e vista amministrativa'
status: To Do
assignee: []
created_date: '2026-11-10T18:00:00Z'
labels:
  - auditor
  - frontend
  - doctor
milestone: m-2
dependencies:
  - TASK-80
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
I controlli notturni sono un argomento di fiducia: l'utente deve poter vedere che i numeri del suo portafoglio sono stati verificati, e l'amministratore deve vedere a colpo d'occhio cosa non va. Il testo per l'utente deve essere sobrio: niente allarmi su difetti che non può risolvere.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Il Doctor mostra un indicatore discreto «Calcoli verificati: N controlli superati» con la data dell'ultima corsa, per portafoglio singolo e vista aggregata
- [ ] #2 Aprendo l'indicatore l'utente vede l'elenco dei controlli per titolo, raggruppati per area, con l'esito; nessun gergo tecnico né id interni
- [ ] #3 Se un controllo fallisce sul suo portafoglio, il testo dice in modo neutro che un calcolo è in verifica e quale area riguarda; se la corsa è vecchia di oltre due giorni o assente, l'indicatore non compare
- [ ] #4 La pagina Admin mostra l'ultima corsa: regole che falliscono, numero di portafogli coinvolti, da quando, severità
- [ ] #5 Privacy Mode, temi di colore e mobile sono rispettati; test dei componenti coprono tutti gli stati
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/frontend/valore-frontend/src/components/doctor/AuditIndicator.tsx` e test, il client in `services/api/`, il montaggio in `pages/Doctor.page.tsx` (modifica minima) e in `pages/Admin.page.tsx`.
Serve un endpoint utente di sola lettura sugli esiti dei propri portafogli: se TASK-80 non lo prevede, aggiungerlo qui nel backend con `require_auth` e verifica della proprietà dello scope.
<!-- SECTION:NOTES:END -->
