---
id: TASK-98
title: 'Tema natalizio: accento rosso su tab e navigazione'
status: Done
assignee: []
created_date: '2026-11-22T10:00:00Z'
labels:
  - frontend
  - ux
dependencies:
  - TASK-97
priority: low
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Feedback: il tema "Natale" (verde abete) è troppo simile a Petrolio. Si aggiunge un accento rosso natalizio (mirtillo rosso) all'interfaccia di navigazione: etichetta e indicatore della tab attiva, pillola attiva delle Impostazioni, voce attiva della barra in basso su mobile. Pulsanti, link, grafici e riempimenti primari restano verde abete; numeri, badge e testi colorati per valore (guadagni/perdite/avvisi) mantengono i colori semantici, così il rosso non si confonde con le perdite.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `colorTheme.ts`: `ColorTheme.accent` (tupla) e `hasOwnAccent`; solo `christmas` definisce un accento proprio, per gli altri temi `accent` = `primary` (aspetto invariato, screenshot identici al pixel per Petrolio e Oceano)
- [x] #2 Accento Natale sugli stessi ruoli del primario: shade 6 ≥4.5:1 su bianco e lightPageBg, shade 4 ≥4.5:1 su dark[6]/dark[7], bianco su shade 8/9 ≥4.5:1; tinta ~353° (lato blu del rosso) distinta dal rosso perdite (~5°)
- [x] #3 `mantineTheme.tsx` (estratto da `main.tsx`): colore Mantine `accent`, default `color: 'accent'` su Tabs; con accento proprio la tab attiva (default/outline) prende anche l'etichetta in `--mantine-color-accent-text` (classe `v365-accent-tab`, regola in `index.css`); le pillole restano testo bianco su riempimento accento
- [x] #4 `MobileBottomNav`: voce attiva con gradiente accento 6→9; il pulsante "+" resta nel colore di marca
- [x] #5 Test: tupla accento e contrasti, accento = primario negli altri temi, render di Tabs con il tema Natale (`--tabs-color`, classe, variabili CSS); suite frontend, typecheck ed eslint verdi
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accento Natale: `#fdecee #fad3d7 #f3a7ae #ee7f88 #e8555c #d63a48 #c3283a #ad2233 #9a1e2e #761725` (shade 6 e 4 riprendono i toni rossi già usati nel campione del selettore, che ora li legge dalla tupla).
Contrasti: shade 6 `#c3283a` su bianco 5.70:1, su lightPageBg 5.37:1; shade 4 `#e8555c` su dark[6] 4.69:1, su dark[7] 5.18:1; bianco su shade 8 8.08:1, su shade 9 10.94:1.
La barra laterale desktop (NavLink) non ha uno stato attivo oggi, quindi non riceve l'accento: aggiungerlo cambierebbe tutti i temi. Nessun `<Tabs>` passa un `color` esplicito, quindi il default vale ovunque. `index.html` invariato: l'accento non serve prima del primo paint.
<!-- SECTION:NOTES:END -->
