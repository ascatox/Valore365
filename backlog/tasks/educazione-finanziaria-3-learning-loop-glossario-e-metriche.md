---
title: "Educazione finanziaria 3: glossario, learning loop e metriche"
status: "Done"
priority: "medium"
created: 2026-03-28
labels: ["education", "frontend", "analytics", "ux", "feature"]
---

# Educazione finanziaria 3: glossario, learning loop e metriche

## Contesto

Dopo aver introdotto template educativi e UI contestuale, manca il livello che consolida l'apprendimento e misura se il nuovo flusso produce davvero comprensione e ritorno.

Senza questo step, il prodotto aggiunge contenuto ma non sa se l'utente ha imparato qualcosa o se il Doctor e' diventato piu' chiaro.

## Obiettivo

Chiudere il loop educativo con tre elementi:

1. glossario contestuale
2. riepilogo "cosa hai imparato oggi"
3. tracciamento eventi minimi per misurare utilizzo e apprendimento

## Scope minimo

### 1. Glossario contestuale

Prima versione con 5 termini:

- diversificazione
- concentrazione
- volatilita'
- overlap
- TER

Ogni voce deve includere:

- definizione semplice
- esempio breve legato al portafoglio
- testo breve e consistente

### 2. Widget "Oggi hai imparato"

Mostrare un riepilogo sintetico dopo la lettura del Doctor o dopo un quick prompt educativo.

Il widget deve essere costruito con logica deterministica a partire da:

- alert visti
- education block aperti
- eventuali risposte del Copilot gia' contestualizzate

### 3. Eventi e metriche

Introdurre tracking minimo per:

- apertura dettaglio alert
- click su CTA educativa
- apertura glossario
- uso quick prompt
- ritorno alla pagina Doctor

Se il progetto non ha ancora un layer analytics strutturato, iniziare con eventi locali o logging minimo ma con naming coerente.

## File coinvolti

- nuovo file `src/frontend/valore-frontend/src/components/doctor/GlossaryTooltip.tsx`
- `src/frontend/valore-frontend/src/components/doctor/DoctorAlertDetailsModal.tsx`
- `src/frontend/valore-frontend/src/pages/Doctor.page.tsx`
- eventuali hook/store frontend per tracking o stato locale apprendimento

## Criteri di accettazione

- [ ] Esiste un glossario contestuale con almeno 5 termini
- [ ] L'utente vede un riepilogo "Oggi hai imparato"
- [ ] Gli eventi minimi del flusso educativo sono tracciati
- [ ] Le metriche possono essere lette almeno in forma basica per validazione prodotto
- [ ] Il nuovo layer non dipende dalla chat libera

## Ordine di implementazione consigliato

1. Definire il catalogo glossario
2. Implementare `GlossaryTooltip.tsx`
3. Definire la logica del widget "Oggi hai imparato"
4. Aggiungere il tracking degli eventi chiave
5. Validare il funnel base con sessioni reali o test interni
