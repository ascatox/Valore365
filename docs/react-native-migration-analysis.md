# Analisi Migrazione React Native - Valore365

## Sommario Esecutivo

La migrazione da React Web a React Native è **fattibile ma di complessità medio-alta**. Il livello di business logic riutilizzabile è buono (~60-70%), ma l'intero layer UI (Mantine) e diverse API web-specific devono essere sostituite. Stima di effort: **3-5 mesi** per un team di 2 sviluppatori.

---

## 1. Architettura Attuale

| Aspetto | Tecnologia | Versione |
|---------|-----------|----------|
| Framework | React + TypeScript | 18.2 / 5.2 |
| Build Tool | Vite | 5.2 |
| UI Library | Mantine | 7.0 |
| State Management | React Query | 5.90 |
| Routing | react-router-dom | 7.13 |
| Charting | Recharts | 3.7 |
| Auth | Clerk | 5.61 |
| Icons | Tabler Icons + Lucide | 3.36 / 0.400 |
| API Layer | fetch nativo (custom wrapper) | - |

**Dimensioni del progetto**: ~62 componenti, 10 pagine, 12 moduli API service.

---

## 2. Cosa si può riutilizzare direttamente (60-70%)

### 2.1 Layer API (`services/api/`) - Riutilizzo ~95%
Il client API usa `fetch` nativo, già supportato in React Native. La struttura dei servizi (portfolio, performance, doctor, assets, transactions, market, import, pac, settings) può essere portata quasi invariata.

**Modifiche necessarie**:
- Sostituire `setTokenGetter` con il meccanismo auth di RN (Clerk ha un SDK RN)
- Nessun'altra modifica significativa

### 2.2 React Query Hooks - Riutilizzo ~90%
`@tanstack/react-query` funziona nativamente su React Native. Tutti i query hooks (portfolio summary, holdings, health checks, X-Ray) possono essere riutilizzati.

### 2.3 Business Logic - Riutilizzo ~95%
- Formatters (numeri, date, valute) in `dashboard/formatters.ts`
- Costanti e tipi TypeScript
- Logica di calcolo (rebalance, FIRE, analisi)
- Tipi API condivisi (`services/api/types.ts`)

### 2.4 Feature Flags e Configurazione - Riutilizzo ~100%
Il file `features.ts` e la struttura di configurazione sono indipendenti dalla piattaforma.

---

## 3. Cosa deve essere riscritto (30-40%)

### 3.1 UI Layer Completo - Riscrittura totale

**Mantine → React Native Paper / NativeBase / Tamagui**

Mantine non ha una versione React Native. Ogni componente UI deve essere riscritto:

| Componente Mantine | Alternativa RN |
|---|---|
| `AppShell` | React Navigation + layout custom |
| `Modal` | React Native Modal / Bottom Sheet |
| `Drawer` | `@react-navigation/drawer` |
| `Table` | `FlatList` / `SectionList` custom |
| `Tabs` | `@react-navigation/material-top-tabs` |
| `Select`, `TextInput`, `NumberInput` | RN Paper / componenti nativi |
| `Button`, `ActionIcon` | RN Paper / Pressable |
| `Card`, `Paper`, `Badge` | RN Paper equivalenti |
| `Burger`, `NavLink` | React Navigation drawer |
| `SegmentedControl` | `react-native-segmented-control` |
| `useMediaQuery` | `Dimensions` / `useWindowDimensions` |
| `useDisclosure` | Hook custom (semplice da rifare) |

**Effort stimato**: Questo è il blocco di lavoro più grande (~50% dell'effort totale).

### 3.2 Navigazione

**react-router-dom → React Navigation 7**

| Route Web | Screen RN |
|---|---|
| `/` | `DashboardScreen` (Tab Navigator) |
| `/portfolio` | `PortfolioScreen` (Tab o Stack) |
| `/doctor` | `DoctorScreen` (Stack) |
| `/fire` | `FireScreen` (Tab) |
| `/settings` | `SettingsScreen` (Stack) |
| `/creator` | `CreatorScreen` (Stack con steps) |
| `/about` | `AboutScreen` (Stack) |
| `/admin` | `AdminScreen` (condizionale) |
| `/instant-analyzer` | `InstantAnalyzerScreen` (può essere deep link) |

**Struttura consigliata**:
```
Tab Navigator (bottom tabs)
├── Dashboard (Stack)
├── Portfolio (Stack)
│   ├── Portfolio List
│   ├── Portfolio Detail
│   └── Transaction Form
├── Doctor (Stack)
├── FIRE (Stack)
└── Settings (Stack)
    └── About
```

### 3.3 Grafici

**Recharts → alternativa RN**

Recharts non supporta React Native. Opzioni:

| Libreria | Pro | Contro |
|---|---|---|
| `react-native-gifted-charts` | API semplice, buona documentazione | Meno personalizzabile |
| `victory-native` | Potente, API simile a Recharts | Più pesante |
| `react-native-skia` + custom | Massima personalizzazione | Effort alto |
| `react-native-wagmi-charts` | Ottima per finance | Limitata a line/candle |

**Consiglio**: `victory-native` per la similarità con Recharts e la copertura di tutti i tipi di grafico usati (Area, Line, Pie/Donut, ComposedChart).

Grafici da migrare:
- Monte Carlo projections (area charts con bande di confidenza)
- Performance timeseries (line/area charts)
- Allocation donut charts
- Analisi comparative

### 3.4 Storage

**localStorage → AsyncStorage / MMKV**

| Web API | RN Equivalente | Note |
|---|---|---|
| `localStorage.getItem` | `AsyncStorage.getItem` (async!) | Tutte le letture diventano async |
| `localStorage.setItem` | `AsyncStorage.setItem` | |
| `localStorage.removeItem` | `AsyncStorage.removeItem` | |

**Attenzione**: Il passaggio da sincrono ad asincrono richiede refactoring di tutti i punti di lettura storage. In alternativa, `react-native-mmkv` offre API sincrone.

**Consiglio**: Usare `react-native-mmkv` per minimizzare il refactoring (API sincrona, performante).

Chiavi da migrare:
- `valore365.selectedPortfolioId`
- `valore365.privacyMode`
- `valore365.brokerDefaultFee`
- `valore365.dashboardChartWindow`
- `valore365.dashboardActiveTab`
- Conversazioni copilot

### 3.5 Custom Events

**window.dispatchEvent → Event Emitter / Zustand**

Il pattern di custom events (`valore365:refresh-dashboard`, `valore365:portfolios-changed`, `valore365:privacy-changed`) non esiste in RN.

Opzioni:
1. **EventEmitter** (e.g., `mitt` o `eventemitter3`) - sostituzione 1:1
2. **Zustand store** - più idiomatico per RN, permette di centralizzare stato globale
3. **React Query invalidation** - per i refresh, già disponibile

**Consiglio**: Eliminare i custom events e usare `queryClient.invalidateQueries()` per i refresh + un piccolo Zustand store per lo stato UI globale (privacy mode, selected portfolio).

### 3.6 API Web-Specific

| API Web | Sostituzione RN |
|---|---|
| `window.URL.createObjectURL` | `react-native-fs` / `react-native-share` |
| `document.querySelector` | Non necessario (no DOM) |
| `window.scrollY` | `ScrollView onScroll` |
| `window.visualViewport` | `Keyboard` API di RN |
| `window.innerHeight` | `Dimensions.get('window')` |
| `Intl.DateTimeFormat` | Supportato in RN (con Hermes) |
| `html-to-image` | `react-native-view-shot` |

---

## 4. Autenticazione

Clerk offre `@clerk/clerk-expo` per React Native/Expo. La migrazione è relativamente semplice:

- `<ClerkProvider>` → `<ClerkProvider>` (stessa API)
- `useAuth()` → `useAuth()` (stessa API)
- `<SignedIn>`, `<SignedOut>` → stessi componenti
- `<UserButton>` → componente custom (non disponibile in RN)
- Token bridge → pattern simile con `getToken()`

**Effort**: Basso, grazie al supporto ufficiale di Clerk per Expo/RN.

---

## 5. Strategia di Migrazione Consigliata

### Approccio: Expo + React Native (non bare workflow)

**Perché Expo**:
- Setup più rapido
- OTA updates
- EAS Build per CI/CD
- Supporto Clerk nativo
- Community più ampia

### Fasi

#### Fase 1: Setup e Infrastruttura (2-3 settimane)
- Inizializzare progetto Expo con TypeScript
- Configurare React Navigation (tab + stack navigators)
- Configurare React Query (copia della config web)
- Portare il layer API services (quasi invariato)
- Configurare Clerk per Expo
- Setup storage (MMKV)
- Setup tema e design system base

#### Fase 2: Schermate Core (4-6 settimane)
- Dashboard (summary, holdings list, grafici performance)
- Portfolio management (lista, dettaglio, transazioni)
- Forms (aggiunta transazione, creazione portfolio)

#### Fase 3: Feature Avanzate (3-4 settimane)
- Doctor (Monte Carlo, Stress Test, X-Ray) con grafici
- FIRE calculator
- Creator wizard (multi-step)
- Copilot chat (AI interface)

#### Fase 4: Polish e Funzionalità Piattaforma (2-3 settimane)
- Pull-to-refresh (già concettualmente presente)
- Push notifications
- Biometric auth
- Dark/light mode (Mantine scheme → RN appearance)
- CSV import/export (adattato per mobile)
- Screenshot/share dei grafici

#### Fase 5: Testing e Release (2-3 settimane)
- Test su iOS e Android
- Performance optimization
- App Store / Play Store submission

---

## 6. Struttura Progetto Consigliata

```
valore-mobile/
├── app/                          # Expo Router o screen definitions
│   ├── (tabs)/
│   │   ├── dashboard.tsx
│   │   ├── portfolio.tsx
│   │   ├── doctor.tsx
│   │   ├── fire.tsx
│   │   └── settings.tsx
│   ├── portfolio/[id].tsx
│   ├── creator/
│   └── instant-analyzer.tsx
├── components/                   # UI Components (riscritti)
│   ├── charts/                   # Victory Native charts
│   ├── common/                   # Button, Card, Input, etc.
│   ├── dashboard/
│   ├── portfolio/
│   ├── doctor/
│   └── copilot/
├── services/                     # ← COPIA DA WEB (quasi invariato)
│   └── api/
├── hooks/                        # Custom hooks (adattati)
├── store/                        # Zustand store (nuovo)
├── theme/                        # Design tokens
└── utils/                        # Formatters, helpers (copia da web)
```

---

## 7. Dipendenze RN Principali

```json
{
  "expo": "~52.x",
  "@clerk/clerk-expo": "^2.x",
  "@tanstack/react-query": "^5.x",
  "@react-navigation/native": "^7.x",
  "@react-navigation/bottom-tabs": "^7.x",
  "@react-navigation/native-stack": "^7.x",
  "react-native-paper": "^5.x",
  "victory-native": "^41.x",
  "react-native-mmkv": "^3.x",
  "react-native-view-shot": "^4.x",
  "react-native-share": "^11.x",
  "react-native-reanimated": "^3.x",
  "zustand": "^5.x",
  "eventemitter3": "^5.x"
}
```

---

## 8. Rischi e Considerazioni

### Rischi Alti
1. **Grafici**: La riscrittura dei grafici finanziari (Monte Carlo, performance) è il punto più critico. Victory Native potrebbe non replicare al 100% il look attuale.
2. **Performance tabelle**: Le tabelle di holdings/transazioni con molte righe richiedono virtualizzazione (`FlatList`) ottimizzata.

### Rischi Medi
3. **CSV Import**: L'import CSV/XLSX su mobile è meno intuitivo. Serve integrazione con file picker nativo.
4. **Copilot Chat**: L'interfaccia chat AI richiede gestione della keyboard e scroll precisa su mobile.
5. **html-to-image**: La cattura screenshot dei grafici richiede `react-native-view-shot`, che ha comportamenti diversi.

### Rischi Bassi
6. **Auth**: Clerk ha buon supporto Expo.
7. **API Layer**: Fetch nativo funziona in RN senza modifiche.
8. **React Query**: Funziona identicamente.

---

## 9. Alternativa: PWA / Capacitor

Prima di impegnarsi in una riscrittura RN, valutare:

| Approccio | Pro | Contro |
|---|---|---|
| **React Native** | Performance nativa, UX ottimale, accesso API native | Riscrittura UI completa |
| **Capacitor/Ionic** | Riutilizzo ~90% codice web, effort minimo | Performance inferiore, UX non nativa |
| **PWA** | Zero riscrittura, installabile | Nessun app store, limitazioni iOS |

**Se il goal è "avere un'app negli store" con effort minimo**, Capacitor è l'opzione migliore: permette di wrappare l'app React/Mantine esistente in un container nativo con accesso a push notifications, camera, etc.

**Se il goal è "UX mobile nativa di alta qualità"**, React Native è la scelta giusta ma richiede significativamente più effort.

---

## 10. Conclusione

| Metrica | Valore |
|---|---|
| **Codice riutilizzabile** | ~60-70% (logic, API, queries, types) |
| **Codice da riscrivere** | ~30-40% (UI, navigation, charts, storage) |
| **Complessità complessiva** | Media-Alta |
| **Effort stimato (RN)** | 3-5 mesi (2 sviluppatori) |
| **Effort stimato (Capacitor)** | 2-4 settimane (1 sviluppatore) |
| **Rischio principale** | Riscrittura grafici finanziari |

Il progetto è in buona posizione per la migrazione grazie a:
- Separazione pulita tra UI e business logic
- API layer indipendente dalla piattaforma
- React Query come state manager (cross-platform)
- TypeScript per type safety condivisa
- Componenti mobile-aware già presenti

La decisione chiave è: **React Native (UX nativa, effort alto) vs Capacitor (UX web, effort basso)**.
