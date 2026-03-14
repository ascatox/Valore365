# Creator — Pagina di creazione guidata portafoglio

> Piano di design — 2026-03-14

---

## Visione utente

Sono un utente che apre Valore365 per la prima volta, oppure voglio costruire un
nuovo portafoglio. Oggi la pagina Portfolio mi chiede subito di inserire
transazioni e ticker manualmente: funziona, ma non mi guida.

La pagina **Creator** e' un'esperienza guidata, step-by-step, che mi porta dalla
domanda _"che tipo di investitore sono?"_ fino ad un portafoglio pronto da
monitorare nella dashboard.

---

## User story principali

| # | Come utente voglio... | Per... |
|---|----------------------|--------|
| 1 | Scegliere un **modello di portafoglio** da una libreria (Lazy Portfolio, All Weather, Golden Butterfly, 60/40, ecc.) | partire da una base solida senza dovermi inventare tutto |
| 2 | Rispondere a **poche domande** sul mio profilo (orizzonte, tolleranza rischio, capitale iniziale) | ricevere un suggerimento personalizzato |
| 3 | Vedere un **anteprima visiva** dell'allocazione (donut chart, tabella pesi) prima di confermare | capire cosa sto costruendo |
| 4 | **Personalizzare** i pesi e gli strumenti del modello scelto | adattarlo alle mie esigenze |
| 5 | **Confrontare** 2-3 modelli affiancati (rendimento storico, volatilita', Sharpe) | scegliere con consapevolezza |
| 6 | Dare un **nome** al portafoglio e confermarlo con un click | iniziare subito a monitorarlo |
| 7 | Essere **guidato visivamente** con stepper/wizard chiaro | non perdermi nei passaggi |

---

## Flusso utente (step-by-step)

```
┌─────────────────────────────────────────────────────────┐
│  STEP 1 — Scegli come iniziare                         │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Modello  │  │ Profilo  │  │  Vuoto   │              │
│  │  pronto  │  │ guidato  │  │(avanzato)│              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
                        │
          ┌─────────────┼──────────────┐
          ▼             ▼              ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────┐
│ STEP 2a      │ │ STEP 2b     │ │ STEP 2c      │
│ Libreria     │ │ Questionario│ │ Allocazione   │
│ modelli      │ │ profilo     │ │ manuale       │
│ (cards)      │ │ (3 domande) │ │ (slider %)    │
└──────────────┘ └─────────────┘ └──────────────┘
          │             │              │
          └─────────────┼──────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 3 — Personalizza                                  │
│                                                         │
│  Donut chart interattivo + tabella asset con slider %   │
│  Puoi aggiungere/rimuovere strumenti, cambiare pesi     │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 4 — Anteprima e confronto                         │
│                                                         │
│  Riepilogo allocazione finale                           │
│  Metriche stimate (rendimento, volatilita', Sharpe)     │
│  Opzione: confronta con altro modello                   │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 5 — Nome e conferma                               │
│                                                         │
│  Input nome portafoglio                                 │
│  Riepilogo finale compatto                              │
│  [Crea portafoglio]  →  redirect a Dashboard            │
└─────────────────────────────────────────────────────────┘
```

---

## Libreria modelli portafoglio

Modelli preconfigurati inclusi nella prima versione:

| Modello | Allocazione | Rischio | Note |
|---------|------------|---------|------|
| **All Weather (Dalio)** | 30% Azioni, 40% Obbligazioni lungo, 15% Obbligazioni medio, 7.5% Oro, 7.5% Commodity | Basso | Resiliente in ogni fase di mercato |
| **Golden Butterfly** | 20% Azioni large, 20% Azioni small, 20% Obbligazioni lungo, 20% Obbligazioni breve, 20% Oro | Medio-basso | Bilanciamento tra crescita e protezione |
| **Classic 60/40** | 60% Azioni globali, 40% Obbligazioni aggregate | Medio | Il classico bilanciato |
| **Aggressivo 80/20** | 80% Azioni (50% USA, 20% Europa, 10% Emergenti), 20% Obbligazioni | Alto | Per orizzonte lungo (15+ anni) |
| **100% Azionario Globale** | 60% USA, 25% Europa, 15% Emergenti | Molto alto | Maximum growth, solo per stomaci forti |
| **Pigro Italiano** | 40% Azioni globali, 30% BTP/obblig. EUR, 20% Obbligazioni globali, 10% Oro | Medio | Ottimizzato per investitore italiano (fiscalita') |

Ogni modello include:
- Nome e descrizione breve
- Composizione con ETF suggeriti (ISIN/ticker)
- Badge rischio (colorato: verde/giallo/arancione/rosso)
- Icona rappresentativa

---

## Questionario profilo (percorso guidato)

3 domande rapide per suggerire il modello piu' adatto:

**D1 — Orizzonte temporale**
- [ ] Meno di 5 anni
- [ ] 5-10 anni
- [ ] 10-20 anni
- [ ] Oltre 20 anni

**D2 — Tolleranza al rischio**
_"Se il tuo portafoglio perdesse il 30% in un mese, cosa faresti?"_
- [ ] Venderei tutto subito
- [ ] Venderei una parte per proteggermi
- [ ] Non farei nulla, aspetterei
- [ ] Comprerei di piu' a sconto

**D3 — Obiettivo principale**
- [ ] Proteggere il capitale
- [ ] Crescita moderata con poca volatilita'
- [ ] Massimizzare la crescita nel lungo periodo
- [ ] Generare rendita periodica

In base alle risposte, il sistema suggerisce 1-2 modelli con motivazione breve.

---

## UI / Componenti

### Layout pagina
- `PageLayout` con nuova variante `creator` (gradiente viola/indaco)
- `PageHeader` con eyebrow "Creator" e titolo "Crea il tuo portafoglio"
- **Stepper** Mantine (`<Stepper>`) nella parte alta per mostrare progresso

### Componenti da creare

| Componente | Descrizione |
|-----------|-------------|
| `Creator.page.tsx` | Pagina principale con logica stepper |
| `CreatorMethodPicker.tsx` | Step 1: scelta tra modello/profilo/vuoto (3 card cliccabili) |
| `CreatorModelLibrary.tsx` | Step 2a: griglia card modelli con filtri rischio |
| `CreatorProfileQuiz.tsx` | Step 2b: questionario 3 domande |
| `CreatorManualAllocation.tsx` | Step 2c: allocazione manuale con slider |
| `CreatorCustomize.tsx` | Step 3: editor allocazione (donut + tabella slider) |
| `CreatorPreview.tsx` | Step 4: anteprima con metriche e confronto opzionale |
| `CreatorConfirm.tsx` | Step 5: nome + riepilogo + bottone conferma |
| `AllocationDonutChart.tsx` | Donut chart riutilizzabile (Recharts PieChart) |
| `types.ts` | Tipi: `PortfolioModel`, `AllocationSlot`, `ProfileAnswer` |
| `models.ts` | Dati statici dei modelli portafoglio |

### Struttura cartelle

```
src/components/creator/
├── CreatorMethodPicker.tsx
├── CreatorModelLibrary.tsx
├── CreatorProfileQuiz.tsx
├── CreatorManualAllocation.tsx
├── CreatorCustomize.tsx
├── CreatorPreview.tsx
├── CreatorConfirm.tsx
├── AllocationDonutChart.tsx
├── types.ts
└── models.ts

src/pages/
└── Creator.page.tsx
```

---

## Integrazione con il sistema esistente

### Routing (`App.tsx`)
```tsx
const CreatorPage = lazy(() =>
  import('./pages/Creator.page.tsx').then(m => ({ default: m.CreatorPage }))
);

// In Routes:
<Route path="/creator" element={<CreatorPage />} />
```

### Navigazione (sidebar)
Aggiungere voce nel menu con icona `IconSparkles` o `IconWand`:
```tsx
<NavLink component={Link} to="/creator"
  label={navbarExpanded ? 'Creator' : undefined}
  leftSection={<IconSparkles size={16} />}
/>
```

### Creazione portafoglio (API)
Alla conferma, il Creator chiama le API gia' esistenti:
1. `POST /api/portfolios` — crea il portafoglio con nome
2. `POST /api/portfolios/{id}/target-allocations` — imposta le target allocation
3. Redirect a `/` (Dashboard) con il nuovo portafoglio selezionato

Nessuna nuova API backend necessaria per la prima versione.

### PageLayout
Aggiungere variante `creator` con gradiente viola/indaco:
```tsx
// Light: sfumatura viola chiara
'radial-gradient(circle at top left, rgba(99,102,241,0.10), transparent 24%),
 linear-gradient(180deg, #f5f3ff 0%, #ffffff 26%, #ede9fe 100%)'

// Dark: sfumatura viola scura
`radial-gradient(circle at top left, rgba(99,102,241,0.16), transparent 24%),
 linear-gradient(180deg, ${dark[8]} 0%, ${dark[7]} 24%, ${dark[8]} 100%)`
```

---

## Stato e gestione dati

Tutto lo stato del wizard vive nel componente `Creator.page.tsx` con `useState`:

```ts
interface CreatorState {
  method: 'model' | 'profile' | 'manual' | null;  // Step 1
  selectedModel: string | null;                     // Step 2a
  profileAnswers: ProfileAnswers | null;            // Step 2b
  allocations: AllocationSlot[];                    // Step 3
  portfolioName: string;                            // Step 5
}
```

Non serve state management globale: il wizard e' lineare e autocontenuto.

---

## Responsive / Mobile

- Stepper diventa **verticale** su mobile (`orientation="vertical"`)
- Card modelli passano a **1 colonna** su mobile
- Donut chart si ridimensiona con `ResponsiveContainer`
- Slider allocazione usa la versione touch-friendly di Mantine
- Bottoni "Indietro / Avanti" fissi in basso su mobile (sticky footer)

---

## Ordine di implementazione

| Fase | Cosa | Stima |
|------|------|-------|
| **1** | Struttura pagina + stepper + routing + navigazione | Fondamenta |
| **2** | Step 1 (MethodPicker) + Step 2a (ModelLibrary) + dati modelli | Primo flusso funzionante |
| **3** | Step 3 (Customize) + AllocationDonutChart | Interattivita' core |
| **4** | Step 5 (Confirm) + integrazione API creazione portafoglio | End-to-end funzionante |
| **5** | Step 2b (ProfileQuiz) + logica suggerimento modello | Percorso guidato |
| **6** | Step 2c (ManualAllocation) | Percorso avanzato |
| **7** | Step 4 (Preview) + metriche stimate + confronto | Polish |
| **8** | Variante PageLayout `creator` + animazioni stepper | Estetica finale |

---

## Fuori scope (v1)

- Backtest storico completo dei modelli (richiede dati storici backend)
- Suggerimenti AI tramite Copilot nel wizard
- Import da broker esterni
- Condivisione social del portafoglio creato
- Portafogli modello personalizzati dall'utente (community)

---

## Mockup testuale — Step 1

```
╔══════════════════════════════════════════════════════════╗
║  CREATOR                                                ║
║  Crea il tuo portafoglio                                ║
║  Scegli il percorso che preferisci per iniziare.        ║
║                                                         ║
║  ● Scegli  ○ Personalizza  ○ Anteprima  ○ Conferma     ║
║  ─────────────────────────────────────────────────       ║
║                                                         ║
║  ┌─────────────────┐ ┌─────────────────┐ ┌───────────┐ ║
║  │  ✨ Modello     │ │  📋 Profilo     │ │  ⚙ Vuoto  │ ║
║  │     pronto      │ │    guidato      │ │ (avanzato)│ ║
║  │                 │ │                 │ │           │ ║
║  │ Scegli da una   │ │ Rispondi a 3    │ │ Parti da  │ ║
║  │ libreria di     │ │ domande e       │ │ zero e    │ ║
║  │ portafogli      │ │ ricevi un       │ │ componi   │ ║
║  │ collaudati      │ │ suggerimento    │ │ libera-   │ ║
║  │                 │ │ su misura       │ │ mente     │ ║
║  └─────────────────┘ └─────────────────┘ └───────────┘ ║
╚══════════════════════════════════════════════════════════╝
```

## Mockup testuale — Step 2a (Libreria modelli)

```
╔══════════════════════════════════════════════════════════╗
║  ○ Scegli  ● Modello  ○ Personalizza  ○ Conferma       ║
║  ─────────────────────────────────────────────────       ║
║                                                         ║
║  Filtro: [Tutti] [Basso] [Medio] [Alto]                 ║
║                                                         ║
║  ┌────────────────────────┐ ┌────────────────────────┐  ║
║  │ 🛡  All Weather        │ │ 🦋 Golden Butterfly    │  ║
║  │ Rischio: ■■□□ Basso    │ │ Rischio: ■■■□ Medio    │  ║
║  │                        │ │                        │  ║
║  │ 30% Azioni             │ │ 20% Large cap          │  ║
║  │ 55% Obbligazioni       │ │ 20% Small cap          │  ║
║  │ 15% Commodities        │ │ 40% Obbligazioni       │  ║
║  │                        │ │ 20% Oro                │  ║
║  │ [Seleziona]            │ │ [Seleziona]            │  ║
║  └────────────────────────┘ └────────────────────────┘  ║
║                                                         ║
║  ┌────────────────────────┐ ┌────────────────────────┐  ║
║  │ ⚖  Classic 60/40      │ │ 🚀 Aggressivo 80/20   │  ║
║  │ Rischio: ■■■□ Medio   │ │ Rischio: ■■■■ Alto     │  ║
║  │ ...                    │ │ ...                    │  ║
║  └────────────────────────┘ └────────────────────────┘  ║
║                                                         ║
║  [← Indietro]                            [Avanti →]     ║
╚══════════════════════════════════════════════════════════╝
```

## Mockup testuale — Step 3 (Personalizza)

```
╔══════════════════════════════════════════════════════════╗
║  ○ Scegli  ○ Modello  ● Personalizza  ○ Conferma       ║
║  ─────────────────────────────────────────────────       ║
║                                                         ║
║  ┌──────────────────┐  Allocazione                      ║
║  │                  │                                   ║
║  │   ╭──────╮       │  Azioni globali   ━━━━━━━━░ 40%  ║
║  │  ╱  40%  ╲      │  Obblig. EUR      ━━━━━━░░░ 30%  ║
║  │ │  Azioni │      │  Obblig. globali  ━━━━░░░░░ 20%  ║
║  │  ╲ 30%20%╱      │  Oro              ━━░░░░░░░ 10%  ║
║  │   ╰─10%──╯       │                                   ║
║  │                  │  Totale: 100%  ✓                  ║
║  └──────────────────┘                                   ║
║                                                         ║
║  [+ Aggiungi asset class]                               ║
║                                                         ║
║  [← Indietro]                            [Avanti →]     ║
╚══════════════════════════════════════════════════════════╝
```
