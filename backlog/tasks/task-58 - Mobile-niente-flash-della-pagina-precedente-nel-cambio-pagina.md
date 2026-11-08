---
id: TASK-58
title: "Mobile: niente flash della pagina precedente nel cambio pagina"
status: "Done"
priority: "high"
created: 2026-11-08
labels: ["frontend", "mobile", "ux", "bug"]
---

# Mobile: niente flash della pagina precedente nel cambio pagina

## Contesto

Su mobile, passando da una pagina all'altra dalla bottom nav, per un attimo si vedeva
"un'altra pagina sotto". Cause trovate (misurate con Playwright a 390x844, frame per frame):

- Ogni componente leggeva `useMediaQuery('(max-width: 48em)')` di Mantine, che parte da
  `false` e legge il valore vero in un effect: il primo frame della nuova pagina veniva
  dipinto con il layout desktop e subito dopo passava a quello mobile.
- Lo scroll della finestra non veniva azzerato: la nuova pagina compariva all'offset della
  precedente (a metà pagina, o sulla coda della vecchia mentre cresceva).
- L'unico `<Suspense>` era al livello più alto, attorno a tutto il router: un chunk di pagina
  in caricamento fuori da una transition avrebbe smontato l'intero AppShell.
- Il primo accesso a una tab attendeva il download del chunk della pagina.

## Acceptance Criteria

- [x] #1 Un boundary `<Suspense>` dentro `AppShell.Main` attorno alle route interne: header e bottom nav non si smontano mai durante la navigazione
- [x] #2 La navigazione resta in transition (React Router v7 `BrowserRouter` usa `startTransition` di default): la pagina attuale resta visibile finché la nuova è pronta, senza fallback
- [x] #3 I chunk delle pagine della navigazione vengono precaricati in idle dopo il primo caricamento, con loader condivisi tra `lazy()` e prefetch
- [x] #4 Al cambio di pathname lo scroll torna in cima prima del paint (window e `AppShell.Main`); i cambi di sola query (`?azione=`) non lo toccano; il pull-to-refresh continua a funzionare
- [x] #5 Il primo frame di una pagina montata usa già il layout mobile (`useIsMobile` legge la media query nel primo render)
- [x] #6 `npm run build`, `npm run lint` e `npm test` passano

## Note di implementazione

- `src/hooks/useIsMobile.ts`: `useMediaQuery(..., { getInitialValueInEffect: false })`
  (l'app gira solo nel browser, niente SSR); sostituisce tutte le chiamate
  `useMediaQuery('(max-width: 48em)')`. Stessa opzione per `isLandscape` (App) e `isDesktop` (Doctor).
- `src/App.tsx`: `pageLoaders` riusati da `lazy()` e da `prefetchAppPages()`
  (`requestIdleCallback`, un chunk alla volta); `PageFallback` leggero; Suspense interno;
  `useLayoutEffect` su `location.pathname` per lo scroll.
- Verifica Playwright (viewport mobile, service worker bloccato, API simulate in errore):
  prima della fix il primo frame della nuova pagina aveva padding desktop e `scrollY` 800;
  dopo, layout mobile e `scrollY` 0 dal primo frame, header e bottom nav presenti in ogni
  frame, nessun fallback anche con chunk rallentato di 1,5 s.
