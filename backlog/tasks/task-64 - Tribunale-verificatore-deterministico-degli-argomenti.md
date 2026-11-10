---
id: TASK-64
title: 'Tribunale: verificatore deterministico degli argomenti'
status: Done
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
Un modello può citare un fatto che non esiste, scrivere un numero a memoria o suggerire di comprare un ETF. Nel Tribunale niente di questo deve arrivare all'utente. Serve un controllo deterministico, senza LLM, che riceve gli argomenti prodotti da una voce e il fascicolo, e restituisce gli argomenti ammessi (con i segnaposto sostituiti dai valori formattati) e quelli scartati con il motivo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un argomento è ammesso solo se cita almeno un fatto, tutti i fatti citati esistono nel fascicolo e sono citabili, e ogni segnaposto `{Fn}` nel testo corrisponde a un fatto citato
- [x] #2 Un argomento con cifre scritte fuori dai segnaposto viene scartato
- [x] #3 Un argomento che nomina un ISIN o un ticker assente dal fascicolo, o che contiene un'indicazione esplicita di acquisto o vendita, viene scartato
- [x] #4 Sono applicati i limiti del contratto su lunghezza del testo e numero di argomenti per voce; una replica deve riferirsi a un argomento ammesso di un'altra voce
- [x] #5 Gli argomenti ammessi escono con il testo finale in italiano (valori sostituiti e formattati) e con l'elenco dei fatti citati; gli scartati escono con il codice di scarto del contratto
- [x] #6 Il verificatore è una funzione pura: stesso ingresso, stessa uscita, nessun accesso a rete o database
- [x] #7 Test unitari coprono ogni codice di scarto, i casi limite di formato e un caso con tutti gli argomenti scartati
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
File di proprietà: `src/backend/app/services/tribunal/verifier.py`, `tests/unit/test_tribunal_verifier.py`.
Relazione con TASK-8 (controllo dei numeri nel Copilot): qui la regola è più severa e più semplice, perché i numeri passano solo dai segnaposto. Non dipende da TASK-8; se TASK-8 è già stato fatto, riusare la sua estrazione dei numeri per riconoscere le cifre libere.
Parallelizzabile con TASK-61, 62, 63, 67. Usa l'esempio di fascicolo del contratto come fixture.
<!-- SECTION:NOTES:END -->
