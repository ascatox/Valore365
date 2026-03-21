# Analisi Migrazione React Native - Valore365

## Sommario Esecutivo

**Decisione: React Native (Expo)** — scelta obbligata per il supporto ai widget nativi iOS/Android, requisito non realizzabile con Capacitor o PWA.

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

#### Fase 4: Widget Nativi (2-3 settimane)
- Setup Widget Extension iOS (Xcode, App Groups, entitlements)
- Modulo nativo bridge per shared storage (RN ↔ Widget)
- Widget Portfolio Summary (SwiftUI + Kotlin)
- Widget Performance Chart con sparkline
- Widget Allocation Donut e Rebalance Alert
- Testing widget su dispositivi reali iOS/Android

#### Fase 5: Polish e Funzionalità Piattaforma (2-3 settimane)
- Pull-to-refresh (già concettualmente presente)
- Push notifications
- Biometric auth
- Dark/light mode (Mantine scheme → RN appearance)
- CSV import/export (adattato per mobile)
- Screenshot/share dei grafici
- Background refresh per aggiornamento dati widget

#### Fase 6: Testing e Release (2-3 settimane)
- Test su iOS e Android (app + widget)
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

## 9. Widget Nativi iOS e Android

I widget nativi della home screen sono un requisito chiave e rappresentano il motivo principale per cui **React Native è l'unica scelta possibile**. Capacitor e PWA non supportano questa funzionalità.

### 9.1 Supporto Widget per Piattaforma

| Funzionalità | React Native | Capacitor | PWA |
|---|---|---|---|
| iOS Home Screen Widget (WidgetKit) | Si | No | No |
| Android Home Screen Widget (App Widgets) | Si | No | No |
| iOS Lock Screen Widget | Si | No | No |
| iOS Dynamic Island (Live Activities) | Si | No | No |
| watchOS Complications | Si | No | No |

### 9.2 Architettura Widget iOS (WidgetKit)

I widget iOS vengono scritti in **Swift/SwiftUI** come Widget Extension separata all'interno del progetto Xcode generato da Expo/RN.

```
ios/
├── Valore365/                    # App principale RN
├── Valore365Widget/              # Widget Extension (Swift)
│   ├── Valore365Widget.swift     # Entry point widget
│   ├── PortfolioSummaryWidget.swift
│   ├── PerformanceWidget.swift
│   └── Assets.xcassets
└── Valore365WidgetExtension.entitlements
```

**Comunicazione App ↔ Widget**:
- **App Groups**: Storage condiviso tra app e widget via `UserDefaults(suiteName:)`
- L'app RN scrive i dati portfolio nel shared storage tramite modulo nativo
- Il widget li legge e li renderizza in SwiftUI
- **Timeline Provider**: WidgetKit richiede un `TimelineProvider` che determina quando aggiornare i dati

**Librerie utili**:
- `react-native-shared-group-preferences` — accesso a App Groups da RN
- `@baked-apps/react-native-widget-extension` — helper per setup WidgetKit
- `react-native-widget-center` — gestione timeline widget

### 9.3 Architettura Widget Android (App Widgets)

I widget Android vengono scritti in **Kotlin/Java** come `AppWidgetProvider`.

```
android/
├── app/src/main/
│   ├── java/.../widgets/
│   │   ├── PortfolioSummaryWidget.kt
│   │   ├── PerformanceWidget.kt
│   │   └── WidgetDataProvider.kt
│   ├── res/
│   │   ├── layout/
│   │   │   ├── widget_portfolio_summary.xml
│   │   │   └── widget_performance.xml
│   │   └── xml/
│   │       ├── portfolio_summary_widget_info.xml
│   │       └── performance_widget_info.xml
│   └── AndroidManifest.xml       # Widget receivers
```

**Comunicazione App ↔ Widget**:
- **SharedPreferences**: L'app RN scrive i dati, il widget li legge
- **WorkManager**: Per aggiornamenti periodici in background
- **RemoteViews**: Layout XML per la UI del widget

### 9.4 Widget Proposti per Valore365

#### Widget 1: Portfolio Summary (Small/Medium)
- Valore totale del portfolio selezionato
- Variazione giornaliera (% e valore assoluto)
- Colore verde/rosso in base alla performance
- Tap → apre la Dashboard

#### Widget 2: Performance Chart (Medium/Large)
- Mini grafico sparkline dell'andamento (7g/30g/YTD)
- Valore attuale e variazione
- Tap → apre la Dashboard con il grafico espanso

#### Widget 3: Allocation Donut (Medium)
- Mini donut chart con le top 5 allocazioni
- Percentuali per categoria/asset
- Tap → apre la sezione Holdings

#### Widget 4: Rebalance Alert (Small)
- Indicatore di drift dal target allocation
- Badge con numero di azioni suggerite
- Tap → apre il Doctor

### 9.5 Impatto sui Tempi

I widget aggiungono **2-3 settimane** al piano di migrazione:

| Attività | Effort |
|---|---|
| Setup Widget Extension iOS (Xcode, App Groups, entitlements) | 2-3 giorni |
| Modulo nativo RN per shared storage | 2-3 giorni |
| Widget Portfolio Summary (iOS + Android) | 3-4 giorni |
| Widget Performance Chart (iOS + Android) | 3-4 giorni |
| Widget Allocation / Rebalance Alert | 2-3 giorni |
| Testing e polish cross-platform | 2-3 giorni |
| **Totale** | **~2-3 settimane** |

### 9.6 Considerazioni Tecniche Widget

**Limitazioni WidgetKit (iOS)**:
- I widget sono **read-only** — non possono avere input complessi
- Aggiornamenti limitati (budget di timeline gestito dal sistema)
- SwiftUI obbligatorio — non si può usare React Native nel widget stesso
- Dimensioni fisse: Small (2x2), Medium (4x2), Large (4x4), Extra Large (iPad)

**Limitazioni App Widgets (Android)**:
- Layout limitato a `RemoteViews` (no custom Views arbitrarie)
- Da Android 12+ supporto per Rounded Corners e Dynamic Colors
- Aggiornamenti minimi ogni 30 minuti (o su richiesta dell'app)

**Background Refresh**:
- L'app deve aggiornare i dati widget periodicamente
- iOS: `BGAppRefreshTask` + WidgetKit timeline reload
- Android: `WorkManager` periodic task
- Entrambi richiedono gestione attenta della batteria

---

## 10. Alternativa Scartata: Capacitor / PWA

| Approccio | Widget Nativi | UX | Effort |
|---|---|---|---|
| **React Native** | Si (iOS + Android) | Nativa | 3-5 mesi |
| **Capacitor** | No | Web in wrapper | 2-4 settimane |
| **PWA** | No | Web | Minimo |

**Verdetto**: Capacitor e PWA sono stati scartati perché **non supportano widget nativi**, requisito fondamentale per il progetto.

---

## 11. Conclusione

| Metrica | Valore |
|---|---|
| **Decisione** | React Native (Expo) — unica opzione per widget nativi |
| **Codice riutilizzabile** | ~60-70% (logic, API, queries, types) |
| **Codice da riscrivere** | ~30-40% (UI, navigation, charts, storage, widget) |
| **Complessità complessiva** | Media-Alta |
| **Effort stimato totale** | 4-6 mesi (2 sviluppatori, inclusi widget) |
| **Di cui widget** | ~2-3 settimane |
| **Rischio principale** | Riscrittura grafici finanziari + codice nativo widget |

Il progetto è in buona posizione per la migrazione grazie a:
- Separazione pulita tra UI e business logic
- API layer indipendente dalla piattaforma
- React Query come state manager (cross-platform)
- TypeScript per type safety condivisa
- Componenti mobile-aware già presenti

I widget nativi richiedono competenze **Swift/SwiftUI** (iOS) e **Kotlin** (Android) in aggiunta a React Native, ma rappresentano un forte valore aggiunto per l'esperienza utente mobile.
