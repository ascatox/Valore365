---
id: TASK-68
title: 'Tribunale: interfaccia della seduta'
status: Done
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - doctor
  - tribunale
  - frontend
  - ui
milestone: m-0
dependencies:
  - TASK-67
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
L'utente deve capire in pochi secondi tre cose: cosa pensa ciascuna voce, su quali dati si basa, e dove le voci non sono d'accordo. Questo task costruisce i componenti della seduta, sviluppati sulla fixture di TASK-67 e indipendenti dalla pagina Doctor, che li monterà in TASK-69.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La seduta mostra le tre voci distinguibili per nome e colore, con gli argomenti che compaiono man mano e l'indicazione della fase in corso
- [x] #2 Ogni argomento mostra posizione (punto di forza, criticità, neutro) e i fatti citati come elementi selezionabili che aprono etichetta, valore, fonte e qualità del dato
- [x] #3 Le repliche sono visivamente collegate all'argomento a cui rispondono
- [x] #4 La sintesi presenta punti condivisi, punti contesi con le voci su ciascun lato e domande aperte, senza alcun elemento che suggerisca un vincitore
- [x] #5 Su desktop le voci sono affiancate; su mobile sono impilate o a schede, senza scorrimento orizzontale
- [x] #6 Sono presenti gli stati della specifica: non disponibile con il motivo, pronto, in corso, concluso, errore con ciò che era già arrivato, limite raggiunto; l'avvertenza è sempre visibile
- [x] #7 In Privacy Mode gli importi sono nascosti come nel resto dell'app; i temi di colore selezionabili sono rispettati
- [x] #8 Il numero di argomenti scartati dal verificatore è mostrato con una spiegazione di cosa significa
- [x] #9 Test dei componenti coprono ogni stato, l'apertura di un fatto citato e la resa su mobile
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/frontend/valore-frontend/src/components/doctor/tribunal/` (esclusi `useTribunalSession.ts` e `fixtures/` di TASK-67). Non modificare `Doctor.page.tsx`.
Riferimenti: `docs/tribunale/ui-spec.md`; `components/doctor/lab/DoctorLabSection.tsx` e `components/doctor/policy/` per stile e struttura; i colori devono seguire il tema Mantine (TASK-59), non esadecimali fissi.
<!-- SECTION:NOTES:END -->
