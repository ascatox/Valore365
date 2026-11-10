---
id: TASK-60
title: 'Tribunale: contratto API, schema dei dati e specifica UI'
status: To Do
assignee: []
created_date: '2026-11-10T09:00:00Z'
labels:
  - ai
  - doctor
  - tribunale
  - docs
milestone: m-0
dependencies: []
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il «Tribunale del portafoglio» è una nuova sezione del Doctor: tre voci AI con filosofie d'investimento diverse discutono lo stesso portafoglio, e ogni affermazione deve poggiare su un dato calcolato dal Doctor. L'utente non riceve un verdetto né un consiglio: vede dove le tre letture concordano e dove divergono, con il dato che sostiene ciascuna posizione. Il principio del prodotto resta fermo: il Doctor calcola, l'AI interpreta.

Questo task fissa per iscritto il contratto che tutti gli altri task del Tribunale (TASK-61…71) implementano in parallelo. Senza un contratto unico i sub agenti inventerebbero formati incompatibili. Le decisioni di progetto sono già prese e vanno riportate nei documenti, non ridiscusse:

- **Fascicolo**: elenco di fatti deterministici, ciascuno con id stabile (`F1`, `F2`…), etichetta, valore, unità, valore già formattato in italiano, fonte e qualità del dato. Nessun LLM lo produce.
- **Voci**: «L'indicizzatore» (basso costo, ampia diversificazione, semplicità), «Il fattoriale» (inclinazioni volute, concentrazione consapevole), «Il prudente» (protezione del capitale, reddito, tenuta nei ribassi).
- **Argomento**: oggetto strutturato con voce, tema, posizione (`punto_di_forza` / `criticita` / `neutro`), testo e id dei fatti citati. I numeri non si scrivono nel testo: si usano segnaposto `{F12}` che il backend sostituisce con il valore formattato.
- **Seduta**: fascicolo → apertura (le tre voci in parallelo) → replica (ogni voce risponde ad argomenti delle altre due) → sintesi (punti condivisi, punti contesi, domande aperte per l'utente). Mai un vincitore.
- **Verificatore**: deterministico; un argomento che non supera i controlli viene scartato prima di arrivare all'utente, che vede solo quanti ne sono stati scartati.
- **Trasporto**: SSE come il Copilot (`data: {"type": ..., "content": ...}`), con eventi dedicati.
- **Non è consulenza**: nessuna indicazione di comprare o vendere strumenti specifici; nessuno strumento che non sia già nel portafoglio viene nominato.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Esiste `docs/tribunale/api-contracts.md` con: endpoint (stato, avvio seduta in SSE, ultima seduta salvata), parametri di scope identici al Doctor (portafoglio singolo e vista aggregata), codici di errore, e per ogni evento SSE il nome, l'ordine e lo schema JSON del contenuto con un esempio
- [ ] #2 Il documento definisce gli schemi JSON di fatto, fascicolo, argomento, replica e sintesi, e un esempio completo di seduta coerente dall'inizio alla fine, riusabile come fixture da backend e frontend
- [ ] #3 Esiste `docs/tribunale/architecture.md` con il flusso della seduta, i moduli previsti in `src/backend/app/services/tribunal/` e in `src/frontend/valore-frontend/src/components/doctor/tribunal/`, e quale task possiede quale file
- [ ] #4 Il documento elenca le regole del verificatore, ciascuna con un codice di scarto, e i limiti numerici della seduta (argomenti per voce, lunghezza del testo, numero di fatti, timeout)
- [ ] #5 Esiste `docs/tribunale/ui-spec.md` con la disposizione desktop e mobile, gli stati (non disponibile, pronto, in corso per fase, concluso, errore, limite raggiunto), il testo dell'avvertenza e il comportamento in Privacy Mode
- [ ] #6 I documenti descrivono le tre voci con mandato, temi ammessi e cose che non possono dire, e spiegano perché il Tribunale non costituisce consulenza personalizzata
- [ ] #7 Nessun codice applicativo viene modificato in questo task
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Modello da seguire: `docs/doctor2/` (api-contracts, architecture, ui-spec). Riferimenti nel codice: eventi SSE in `src/backend/app/copilot/providers.py` (`_sse`) e `copilot/streaming.py`; scope e feature flag in `src/backend/app/api/routes_doctor.py`; metriche in `src/backend/app/services/doctor_policy/metrics.py`.
Eventi SSE attesi (nomi da confermare nel contratto): `phase`, `case_file`, `argument`, `rebuttal`, `synthesis`, `discarded`, `done`, `error`.
Sblocca tutti gli altri task: va fatto per primo e da un solo agente.
<!-- SECTION:NOTES:END -->
