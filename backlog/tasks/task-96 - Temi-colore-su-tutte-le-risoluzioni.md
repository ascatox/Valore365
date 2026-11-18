---
id: TASK-96
title: Temi colore su tutte le risoluzioni
status: Done
assignee: []
created_date: '2026-11-18T07:30:00Z'
labels:
  - frontend
  - ux
dependencies:
  - TASK-59
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
I temi colore ("Tema colore" in Impostazioni > Generale, introdotti da TASK-59) si applicavano solo su viewport da telefono (≤48em): su tablet e desktop l'app restava sempre su Petrolio e il selettore era nascosto. Ora il tema scelto vale a ogni risoluzione (telefono, tablet, desktop) e il selettore è visibile ovunque.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `colorTheme.ts`: il tema attivo coincide sempre con la preferenza salvata, senza controllo del viewport né listener `matchMedia` (resta il listener `storage`)
- [x] #2 `index.html`: lo script prima del primo paint imposta `data-v365-theme` da localStorage senza controllo del viewport
- [x] #3 Impostazioni: il selettore "Tema colore" è visibile a ogni risoluzione (desktop: 6 colonne, 3 con testo grande; mobile: 3, 2 con testo grande) e la descrizione dice "Vale per questo dispositivo."
- [x] #5 Nessun colore di marca hard-coded fuori dalle tuple del tema: landing e Instant Analyzer (visibili anche su desktop) usano `teal`/`dark` con gli stessi ruoli di Petrolio (chiaro: shade 6 e lightPageBg; scuro: shade 4, dark[7]/dark[6]/dark[4]); un test lo verifica insieme ai ruoli e al contrasto di ogni tema
- [x] #4 Test aggiornati: il tema si applica anche su desktop e il selettore compare su desktop; suite frontend, typecheck ed eslint verdi
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Rimosso `MOBILE_QUERY` e lo stato `currentActive` da `src/colorTheme.ts` (`getActiveColorTheme` restituisce il tema della preferenza; API invariata). Aggiornati commento e script in `index.html`, selettore e testo in `Settings.page.tsx`, test in `colorTheme.test.ts` e `Settings.colorTheme.test.tsx`, e la nota in `docs/tribunale/ui-spec.md`.
Coerenza dei temi in chiaro e scuro: sostituiti i colori smeraldo fissi (#10b981, #059669, #ecfdf5, #a7f3d0, #f0fdf4, #065f46, #064e3b, rgba(16,185,129,…)) in `LandingPage`, `InstantPortfolioAnalyzerPage` e `components/instant-analyzer/*` con `theme.colors.teal[n]` / `var(--mantine-color-teal-n)`; sfondi di sezione chiari su `var(--v365-page-bg)`. Lo sfondo pagina (`index.css`) non ha media query: vale già a ogni risoluzione. Restano fissi: palette dei grafici, colori semantici, `AiReadyBadge` (marchio esterno) e il manifest PWA statico.
<!-- SECTION:NOTES:END -->
