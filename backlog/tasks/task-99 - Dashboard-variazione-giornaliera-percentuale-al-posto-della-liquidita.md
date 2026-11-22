---
id: TASK-99
title: 'Dashboard: variazione giornaliera percentuale al posto della liquidità'
status: Done
assignee: []
created_date: '2026-11-22T11:30:00Z'
labels:
  - frontend
  - ux
dependencies: []
priority: low
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Richiesta: togliere la voce CASH dalla riga KPI della Dashboard (Panoramica) e mettere al suo posto la variazione giornaliera percentuale con il simbolo, separandola dall'importo guadagnato/perso, che resta nella sua card. Le due coppie diventano simmetriche: "Var. Giornaliera" (importo) / "Var. Giornaliera %" e "P/L Totale" / "P/L %". Su mobile la liquidità esce dal carosello KPI e il badge "oggi" dell'hero mostra solo l'importo. La liquidità resta nelle altre pagine (Portfolio, modali di ribilanciamento) e nelle API/tipi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Desktop/tablet: la card "Var. Giornaliera" mostra solo l'importo con segno e colore guadagno/perdita; niente più percentuale tra parentesi né mini-gauge
- [x] #2 La card "Cash" è rimossa e "Var. Giornaliera %" apre la riga (ordine: Var. Giornaliera %, Var. Giornaliera, Valore Totale, P/L Totale, P/L %) (segno, %, colore per segno, freccia su/giù a destra), costruita come "P/L %": stesso stile icona, N/D senza dati, percentuale non mascherata in modalità privacy (l'importo sì)
- [x] #3 Mobile: "Liquidità" esce dal carosello e "Var. giorn. %" è la prima card; il badge "oggi" dell'hero mostra solo l'importo
- [x] #4 I valori stanno su una riga anche a ~1024px con la barra laterale aperta (dimensione del valore con unità container query), icona flottante in alto a destra (la seconda riga dell'etichetta scorre sotto), spazio indivisibile prima di "%" così l'etichetta va al massimo su due righe, valori allineati in basso
- [x] #5 Pulizia: rimossi `MiniGauge` e le prop inutilizzate di `KpiStatCardProps` (`gaugeValue`, `subtitle`, `subtitleColor`, `diff`, `diffLabel`) e i rami `isMobile` morti nelle card desktop
- [x] #6 Test: nuovo `PanoramicaTab.test.tsx` (ordine card, niente cash, importo/percentuale separati, colori e frecce, privacy, N/D, variante mobile); suite frontend, typecheck ed eslint verdi
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
La freccia direzionale (su-destra se ≥0, giù-destra se <0, colore per segno) ora vale per entrambe le card percentuali: prima "P/L %" mostrava sempre una freccia verde verso l'alto anche in perdita. La card dell'importo giornaliero usa un'icona neutra (orologio, arancio) come "P/L Totale" usa l'icona attività. Il mini-gauge era usato solo qui ed è stato eliminato. Non esiste uno skeleton di caricamento per la riga KPI: durante il caricamento tutte le card mostrano N/D, comportamento invariato. Verifica visiva con Playwright e API simulate a 1366, 1024 e 390px (tema scuro).
<!-- SECTION:NOTES:END -->
