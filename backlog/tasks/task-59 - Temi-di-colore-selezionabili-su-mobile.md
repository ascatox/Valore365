---
id: TASK-59
title: Temi di colore selezionabili su mobile
status: In Progress
assignee: []
created_date: '2026-11-10T06:48:00Z'
labels:
  - frontend
  - mobile
  - ux
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Su mobile l'app ha un solo colore di marca (Petrolio). Si vuole dare all'utente la possibilità di personalizzare l'aspetto scegliendo tra più temi di colore, senza toccare l'esperienza desktop.

Su viewport da telefono (≤48em) l'utente sceglie tra 6 temi di colore — Petrolio (predefinito), Oceano, Ametista, Orchidea, Bronzo, Grafite — in Impostazioni > Generale, alla voce "Tema colore". La scelta è salvata sul dispositivo (localStorage), si applica subito e funziona sia in chiaro sia in scuro. Su desktop l'app mantiene il tema Petrolio e il selettore è nascosto.

I colori di marca scritti a mano nell'app vanno sostituiti con variabili di tema, così che con un altro tema non resti nulla color petrolio. I colori semantici (guadagno, perdita, attenzione) non fanno parte del tema e non cambiano.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Il selettore "Tema colore" è visibile in Impostazioni > Generale solo su mobile (≤48em) e offre almeno 5 temi oltre a Petrolio; il tema predefinito Petrolio resta identico a oggi
- [ ] #2 Il tema scelto si applica subito, senza ricaricare, e resta dopo il ricaricamento della pagina (salvato su localStorage); all'avvio non si vede alcun flash dei colori predefiniti
- [ ] #3 Su desktop (>48em) il selettore è nascosto e l'app usa sempre il tema Petrolio, anche se sul dispositivo è salvato un altro tema
- [ ] #4 Ogni tema è leggibile in modalità chiara e scura: il testo sui riempimenti di marca rispetta il contrasto WCAG AA
- [ ] #5 Con un tema diverso da Petrolio nessun elemento dell'app resta color petrolio: i colori di marca fissi sono sostituiti da variabili di tema
- [ ] #6 I colori di guadagno, perdita e attenzione sono identici in tutti i temi
- [ ] #7 npm test, npm run lint e npm run build passano
<!-- AC:END -->
