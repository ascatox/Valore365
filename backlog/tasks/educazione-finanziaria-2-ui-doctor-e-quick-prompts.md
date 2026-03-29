---
title: "Educazione finanziaria 2: UI Doctor e quick prompts contestuali"
status: "Done"
priority: "high"
created: 2026-03-28
labels: ["education", "doctor", "copilot", "frontend", "ux", "feature"]
---

# Educazione finanziaria 2: UI Doctor e quick prompts contestuali

## Contesto

Il frontend ha gia' il dettaglio alert del Doctor e il Copilot, ma i due layer non sono ancora collegati da un'esperienza educativa guidata.

Riferimenti principali:

- `src/frontend/valore-frontend/src/components/doctor/DoctorAlertDetailsModal.tsx`
- `src/frontend/valore-frontend/src/pages/Doctor.page.tsx`
- `src/frontend/valore-frontend/src/components/copilot/CopilotChat.tsx`
- `src/frontend/valore-frontend/src/services/api/doctor.ts`

## Obiettivo

Rendere ogni alert del Doctor comprensibile senza chat libera e permettere all'utente di aprire il Copilot con prompt rapidi e contestuali.

## Scope minimo

### 1. Education block nel dettaglio alert

Nel modal del Doctor mostrare un blocco dedicato con:

- Cosa significa
- Perche' conta
- Come leggerlo nel tuo portafoglio
- Concetto chiave

Estrarre il rendering in un componente dedicato, ad esempio:

- `src/frontend/valore-frontend/src/components/doctor/EducationBlock.tsx`

### 2. Quick prompts per alert

Per ogni alert con payload education mostrare 2-3 CTA, ad esempio:

- `Spiegamelo semplice`
- `Perche' conta davvero?`
- `Cosa potrei sistemare prima?`

Le CTA non devono aprire una chat vuota: devono inviare un prompt gia' costruito a partire dal contesto alert.

### 3. Passaggio contesto al Copilot

Quando l'utente parte dal Doctor, il frontend deve passare almeno:

- `page_context=doctor`
- `alert_type`
- titolo alert o concetto chiave
- eventuali metriche sintetiche utili

Se serve, estendere la request del Copilot o il costruttore dei quick prompt nel frontend.

### 4. Copy e UX coerenti

Vincoli:

- linguaggio semplice
- testo breve
- nessuna consulenza
- nessun sovraccarico visivo nel modal

## File coinvolti

- `src/frontend/valore-frontend/src/components/doctor/DoctorAlertDetailsModal.tsx`
- nuovo file `src/frontend/valore-frontend/src/components/doctor/EducationBlock.tsx`
- `src/frontend/valore-frontend/src/pages/Doctor.page.tsx`
- `src/frontend/valore-frontend/src/components/copilot/CopilotChat.tsx`
- `src/frontend/valore-frontend/src/services/api/doctor.ts`

## Criteri di accettazione

- [ ] Ogni alert con payload education mostra il blocco educativo nel modal
- [ ] Le CTA rapide inviano un prompt contestuale, non una chat vuota
- [ ] Il Copilot riceve il contesto `doctor`
- [ ] L'utente puo' capire il senso base dell'alert senza dover scrivere manualmente
- [ ] La UI resta leggibile su desktop e mobile

## Ordine di implementazione consigliato

1. Integrare il payload education nel client API frontend
2. Creare `EducationBlock.tsx`
3. Montarlo nel `DoctorAlertDetailsModal`
4. Aggiungere quick prompts contestuali
5. Verificare il passaggio del contesto al Copilot
