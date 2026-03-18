---
title: "Creator: completare le pagine di creazione portafoglio mancanti"
status: "To Do"
priority: "high"
created: 2026-03-18
labels: ["frontend", "creator", "feature"]
---

# Creator: completare le pagine di creazione portafoglio mancanti

## Contesto

La pagina Creator (`/creator`) ha attualmente solo il percorso "Modello pronto" funzionante (Fasi 1-4 del piano).
I percorsi "Profilo guidato" e "Allocazione manuale" sono disabilitati con badge "Prossimamente", e la pagina di anteprima/confronto non e' implementata.

Riferimento: `backlog/docs/FEATURE_CREATOR_PAGE.md`

## Pagine da implementare

### 1. CreatorProfileQuiz (Step 2b) — Profilo guidato
- **File:** `src/frontend/valore-frontend/src/components/creator/CreatorProfileQuiz.tsx`
- **Descrizione:** Questionario con 3 domande rapide (orizzonte temporale, tolleranza rischio, obiettivo)
- **Output:** Suggerimento di 1-2 modelli dalla libreria con motivazione breve
- **Logica:** Mappatura risposte → profilo rischio → modelli consigliati
- **Abilitare** il percorso "Profilo guidato" nel `CreatorMethodPicker`

### 2. CreatorManualAllocation (Step 2c) — Allocazione manuale
- **File:** `src/frontend/valore-frontend/src/components/creator/CreatorManualAllocation.tsx`
- **Descrizione:** Interfaccia per comporre un portafoglio da zero con slider percentuali
- **Funzionalita':**
  - Ricerca e aggiunta asset class / ETF
  - Slider per regolare i pesi (con vincolo totale = 100%)
  - Donut chart interattivo (riutilizzare `AllocationDonutChart`)
  - Bottone "+ Aggiungi asset class"
- **Abilitare** il percorso "Allocazione manuale" nel `CreatorMethodPicker`

### 3. CreatorPreview (Step 4) — Anteprima e confronto
- **File:** `src/frontend/valore-frontend/src/components/creator/CreatorPreview.tsx`
- **Descrizione:** Riepilogo allocazione finale con metriche stimate
- **Funzionalita':**
  - Visualizzazione riepilogativa dell'allocazione scelta
  - Metriche stimate: rendimento atteso, volatilita', Sharpe ratio
  - Confronto opzionale con un altro modello (side-by-side)
- **Note:** Richiede dati storici o stime statiche per le metriche

## Ordine di implementazione consigliato

1. **CreatorProfileQuiz** (Fase 5 del piano) — piu' semplice, alto valore UX
2. **CreatorManualAllocation** (Fase 6) — percorso avanzato per utenti esperti
3. **CreatorPreview** (Fase 7) — polish, richiede dati per metriche

## File coinvolti

- `src/frontend/valore-frontend/src/pages/Creator.page.tsx` — aggiungere nuovi step
- `src/frontend/valore-frontend/src/components/creator/CreatorMethodPicker.tsx` — abilitare i 2 percorsi disabilitati
- `src/frontend/valore-frontend/src/components/creator/types.ts` — eventuali nuovi tipi (`ProfileAnswers`, ecc.)
- `src/frontend/valore-frontend/src/components/creator/models.ts` — logica mappatura profilo → modello

## Criteri di accettazione

- [ ] Il percorso "Profilo guidato" e' abilitato e funzionante end-to-end
- [ ] Il percorso "Allocazione manuale" e' abilitato e funzionante end-to-end
- [ ] La pagina di anteprima mostra metriche e permette il confronto tra modelli
- [ ] Tutti e 3 i percorsi portano alla creazione del portafoglio via API esistenti
- [ ] Responsive: funziona su mobile e desktop
