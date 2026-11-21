---
id: TASK-97
title: Tema natalizio
status: Done
assignee: []
created_date: '2026-11-21T10:00:00Z'
labels:
  - frontend
  - ux
dependencies:
  - TASK-96
priority: low
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Nuovo tema colore "Natale" (id `christmas`) in Impostazioni > Generale > Tema colore, ultimo della lista. Il colore di marca è un verde abete profondo, tendente al blu e poco saturo, così non si confonde con il verde dei guadagni (né il rosso natalizio con le perdite); i neutri scuri hanno una leggera tinta d'abete (notte d'inverno) e lo sfondo chiaro è un bianco neve caldo. Il tocco festivo è nel campione del selettore: verde abete + rosso natalizio.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `colorTheme.ts`: tema `christmas` / "Natale" in fondo alla lista, con tuple `teal` e `dark` sugli stessi ruoli e passi di luminanza di Petrolio (bianco su shade 6 ≥4.5:1, shade 4 su dark[6]/dark[7] ≥4.5:1, tuple monotone, lightPageBg quasi bianco)
- [x] #2 Il verde abete si distingue dal verde dei guadagni (tinta ~155° contro ~142°, saturazione molto più bassa); il rosso compare solo nel campione, mai nell'interfaccia
- [x] #3 Campione del selettore personalizzabile per tema (`swatchOverride`, con toni distinti per chiaro e scuro): Natale mostra abete + rosso in entrambe le modalità, gli altri temi restano invariati
- [x] #4 `index.html`: regola pre-paint per lo sfondo chiaro di `christmas`
- [x] #5 Impostazioni: su desktop una riga con tutti i temi (7 colonne; 4 per riga con testo grande); mobile invariato (3, 2 con testo grande)
- [x] #6 Test per il nuovo tema (selettore, `data-v365-theme="christmas"`, campione); suite frontend, typecheck ed eslint verdi
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Tuple generate a partire dalla luminanza relativa di ogni shade di Petrolio (stessi rapporti di contrasto), con tinta 155° per il primario e 145° per i neutri scuri.
- primary: `#e8f4ef #cde9dd #a2d1be #79b79d #529e7e #378665 #2c7757 #286c50 #246249 #1c4a37`
- dark: `#d3ddd7 #a9b7ae #7a8a81 #55625a #2c3831 #1c2821 #16201a #0f1511 #0b110e #070c09`
- lightPageBg `#faf8f2`
Contrasti: bianco su shade 6 5.41:1 (shade 8 7.20:1), shade 6 su lightPageBg 5.09:1, shade 4 su dark[6] 5.22:1 e su dark[7] 5.77:1. Distanza dal verde guadagni (CIELAB ΔE): 21.8 in chiaro (shade 6 vs `#15803d`), 42.6 in scuro (shade 4 vs `#4ade80`).
`ColorTheme` ha ora `swatchDark` oltre a `swatch` (prima l'inversione per le card scure era nel selettore): calcolati come `[6, 3]` e `[3, 6]` salvo `swatchOverride`. Natale: chiaro `#2c7757` + `#c3283a`, scuro `#529e7e` + `#e8555c` (la spunta resta leggibile sul tono principale). Colonne desktop del selettore = numero di temi.
<!-- SECTION:NOTES:END -->
