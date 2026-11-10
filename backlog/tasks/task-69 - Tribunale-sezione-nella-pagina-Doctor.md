---
id: TASK-69
title: 'Tribunale: sezione nella pagina Doctor'
status: Done
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - doctor
  - tribunale
  - frontend
milestone: m-0
dependencies:
  - TASK-65
  - TASK-68
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
I componenti della seduta vanno resi raggiungibili: una quarta sezione «Tribunale» accanto a Diagnosi, I miei parametri e Laboratorio, collegata allo scope selezionato e agli endpoint reali.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La pagina Doctor ha la sezione «Tribunale», visibile solo se la funzione è attiva nelle feature del backend
- [x] #2 La sezione usa lo scope selezionato (portafoglio singolo o vista aggregata) e si azzera quando lo scope cambia
- [x] #3 All'apertura mostra l'ultima seduta salvata, se esiste, con la data e l'indicazione che i dati sono cambiati quando è il caso; l'utente avvia una nuova seduta con un'azione esplicita, mai in automatico
- [x] #4 Se il Copilot non è configurato o il provider non è adatto, la sezione lo spiega e rimanda a Impostazioni → Copilot
- [x] #5 Un errore nella sezione non rompe le altre sezioni del Doctor
- [x] #6 La navigazione su mobile funziona con quattro sezioni senza testo troncato
- [x] #7 Test di pagina coprono visibilità con funzione attiva e spenta, cambio di scope, vista aggregata e Copilot non configurato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/frontend/valore-frontend/src/pages/Doctor.page.tsx` (unico task del Tribunale che lo modifica) e `src/pages/Doctor.tribunal.test.tsx`.
Riferimenti: `DOCTOR_SECTIONS`, `availableSections` e `DoctorSectionErrorBoundary` in `Doctor.page.tsx`; `Doctor.policy.test.tsx` come modello di test.
Se TASK-66 non è ancora chiuso, la parte «ultima seduta» degrada senza errori quando l'endpoint non esiste.
Aggiornamento da TASK-60: TASK-69 possiede anche `DOCTOR_TRIBUNAL_UI_ENABLED` in `src/features.ts`. Impostazioni → Copilot non ha un deep link: il rimando è a `/settings` indicando la scheda a parole.
<!-- SECTION:NOTES:END -->
