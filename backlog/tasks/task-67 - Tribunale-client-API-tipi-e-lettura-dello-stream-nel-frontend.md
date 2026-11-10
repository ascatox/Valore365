---
id: TASK-67
title: 'Tribunale: client API, tipi e lettura dello stream nel frontend'
status: To Do
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - doctor
  - tribunale
  - frontend
milestone: m-0
dependencies:
  - TASK-60
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il frontend deve poter avviare una seduta e ricevere fascicolo, argomenti, repliche e sintesi man mano che arrivano. Questo task crea lo strato dati: tipi TypeScript allineati al contratto, funzioni di chiamata e un hook che trasforma lo stream in uno stato leggibile dai componenti. Include una seduta di esempio registrata, così l'interfaccia (TASK-68) può essere sviluppata senza backend.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 I tipi TypeScript di fatto, fascicolo, argomento, replica, sintesi ed eventi corrispondono agli schemi di `docs/tribunale/api-contracts.md`
- [ ] #2 Esistono le funzioni per stato, avvio seduta e ultima seduta, per portafoglio singolo e vista aggregata, con gli stessi meccanismi di autenticazione del client esistente
- [ ] #3 Un hook espone fase corrente, fascicolo, argomenti per voce, repliche, sintesi, numero di scartati, errore, e le azioni avvia, interrompi e rifai
- [ ] #4 Interrompere la seduta chiude la connessione; cambiare scope o smontare il componente fa lo stesso
- [ ] #5 Eventi sconosciuti o malformati vengono ignorati senza rompere la seduta; un errore a metà conserva ciò che è già arrivato
- [ ] #6 Una fixture con la seduta di esempio del contratto e un finto stream sono disponibili per i test e per TASK-68
- [ ] #7 Test unitari coprono seduta completa, errore a metà, interruzione, evento sconosciuto e limite raggiunto
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/frontend/valore-frontend/src/services/api/tribunal.ts`, i tipi (in un file dedicato, esportati da `services/api/index.ts`), `src/components/doctor/tribunal/useTribunalSession.ts`, `src/components/doctor/tribunal/fixtures/`.
Riferimenti: la lettura SSE in `src/components/copilot/CopilotChat.tsx` (righe attorno al parsing di `event.type`), `services/api/doctor.ts` e `services/api/client.ts`.
Parallelizzabile con TASK-61…64.
<!-- SECTION:NOTES:END -->
