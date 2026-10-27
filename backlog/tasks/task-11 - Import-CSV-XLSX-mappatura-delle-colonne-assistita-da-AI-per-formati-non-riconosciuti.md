---
id: TASK-11
title: >-
  Import CSV/XLSX: mappatura delle colonne assistita da AI per formati non
  riconosciuti
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-27T20:27:00Z'
updated_date: '2026-10-27T20:28:00Z'
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
- [ ] #1 Se le intestazioni non corrispondono a nessun formato noto e l'AI è disponibile, il sistema propone una mappatura colonne del file -> campi della transazione
- [ ] #2 Al modello vengono inviate solo le intestazioni e al massimo 5 righe di esempio
- [ ] #3 La mappatura proposta viene validata (campi obbligatori presenti, date e importi interpretabili) prima di essere applicata
- [ ] #4 L'utente vede la mappatura proposta nell'anteprima, può correggerla, e nessuna transazione viene salvata senza la sua conferma
- [ ] #5 Se l'AI non è configurata o fallisce, il comportamento attuale (errore con messaggio) resta invariato
- [ ] #6 I formati già supportati (generico, Fineco) non passano dall'AI
- [ ] #7 Test con provider simulato su almeno 2 formati di broker non supportati
<!-- AC:END -->
