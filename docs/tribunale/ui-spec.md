# Tribunale del portafoglio — Specifica UI

Stato: **specifica di implementazione** per TASK-67…70. Riferimenti: contratto
`docs/tribunale/api-contracts.md`, architettura `docs/tribunale/architecture.md`, stile e
struttura di `docs/doctor2/ui-spec.md` (Diagnosi, I miei parametri, Laboratorio), seduta di
esempio `docs/tribunale/fixtures/seduta-esempio.json`.

Principi UI:

- Il frontend **non calcola nulla di finanziario** e non riformatta i fatti: mostra
  `formatted` così com'è.
- L'utente deve capire in pochi secondi tre cose: **cosa pensa ciascuna voce, su quali dati si
  basa, dove le voci non sono d'accordo**.
- **Nessun vincitore**, nessun consiglio (§7). L'avvertenza è sempre visibile (§5).
- Una seduta parte solo con un'azione esplicita dell'utente, mai in automatico.

---

## 1. Posizione nella pagina Doctor (TASK-69)

Pagina `src/pages/Doctor.page.tsx`, quarta sezione dopo Diagnosi, I miei parametri e Laboratorio.

| sezione | `?section=` | visibile se |
|---|---|---|
| **Tribunale** | `tribunale` | `DOCTOR_TRIBUNAL_UI_ENABLED` (`src/features.ts`) **e** `GET /api/doctor/features` → `tribunal_enabled: true` (`useTribunalFeature`) |

- Deep link `/doctor?section=tribunale`; con la sezione non disponibile ricade su Diagnosi, come
  le altre sezioni. Finché `/doctor/features` non risponde la tab non è mostrata.
- La sezione usa lo scope del `PortfolioSwitcher` (singolo o aggregato) ed è avvolta in
  `DoctorSectionErrorBoundary` con chiave `tribunale-<id dello scope>`: cambiare scope smonta la
  sezione (lo stream si chiude, lo stato si azzera) e un errore di rendering non tocca le altre
  sezioni.
- **Navigazione con quattro sezioni su mobile** (< 48em): la `Tabs.List` diventa una griglia 2×2
  (`display: grid; grid-template-columns: 1fr 1fr`), etichette intere senza troncamento:
  «Diagnosi», «I miei parametri», «Laboratorio», «Tribunale», ciascuna con icona
  (`IconStethoscope`, `IconAdjustments`, `IconFlask`, `IconScale` di Tabler). Da 48em in su resta la
  riga attuale. Con due o tre sezioni attive vale lo stesso schema (griglia 2 colonne su mobile).
- Nessun salvataggio automatico, nessun avvio automatico: entrare nella sezione legge solo stato
  e ultima seduta.

## 2. Disposizione

### 2.1 Desktop (≥ 62em, Mantine `md`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Avvertenza (sempre visibile, §5)                                             │
├──────────────────────────────────────────────────────────────────────────────┤
│ Intestazione: titolo «Tribunale del portafoglio» · scope · data seduta       │
│ [Fascicolo] → [Apertura] → [Replica] → [Sintesi]         [Interrompi]/[Avvia] │
├────────────────────────┬────────────────────────┬────────────────────────────┤
│ L'indicizzatore        │ Il fattoriale          │ Il prudente                │
│ mandato · stato        │ mandato · stato        │ mandato · stato            │
│ ┌ argomento ────────┐  │ ┌ argomento ────────┐  │ ┌ argomento ────────────┐  │
│ │ badge posizione   │  │ │                   │  │ │                       │  │
│ │ testo con [fatti] │  │ │                   │  │ │                       │  │
│ │  └ replica di …   │  │ │                   │  │ │                       │  │
│ └───────────────────┘  │ └───────────────────┘  │ └───────────────────────┘  │
├────────────────────────┴────────────────────────┴────────────────────────────┤
│ Sintesi: Punti condivisi · Punti contesi (lato A | lato B) · Domande aperte   │
├──────────────────────────────────────────────────────────────────────────────┤
│ Argomenti scartati dal verificatore (conteggi) · Fascicolo (accordion)       │
└──────────────────────────────────────────────────────────────────────────────┘
```

- Le tre colonne hanno **la stessa larghezza** (`SimpleGrid cols={{ base: 1, md: 3 }}`) e
  l'ordine canonico fisso: indicizzatore, fattoriale, prudente (mai riordinate in base agli
  argomenti o all'ordine di arrivo).
- La sintesi occupa tutta la larghezza sotto le colonne; i due lati di un punto conteso sono
  affiancati (`SimpleGrid cols={{ base: 1, sm: 2 }}`), stessa larghezza.

### 2.2 Tablet e mobile (< 62em)

- Le voci diventano **schede** (`Tabs` con `grow`, tre tab: «Indicizzatore», «Fattoriale»,
  «Prudente», ciascuna con il pallino del colore della voce e il numero di argomenti ammessi;
  durante l'attesa un `Loader` piccolo al posto del numero). Una sola voce visibile alla volta,
  nessuno scorrimento orizzontale.
- La sintesi va sotto le schede, sempre visibile (non in una tab); i lati di un punto conteso sono
  impilati sotto 36em (`sm`).
- Il dettaglio di un fatto si apre in un `BottomSheet` (`components/mobile/BottomSheet`) invece che
  in un popover.
- I pulsanti principali sono a tutta larghezza; l'avvertenza resta in cima, compatta.
- Nessun elemento supera la larghezza del viewport (testi lunghi con `overflow-wrap: anywhere`,
  chip dei fatti che vanno a capo).

## 3. Componenti (TASK-68)

Percorsi relativi a `src/frontend/valore-frontend/src/components/doctor/tribunal/`.

| componente / modulo | file | responsabilità |
|---|---|---|
| `TribunalSection` | `TribunalSection.tsx` | contenitore: `useTribunalFeature`/`useTribunalStatus`/`useTribunalLatest`/`useTribunalSession`, macchina degli stati (§4), avvertenza, slot `renderContestedActions` |
| `TribunalDisclaimer` | `TribunalDisclaimer.tsx` | avvertenza (§5) |
| `TribunalStateCard` | `TribunalStateCard.tsx` | stati non disponibile, pronto, errore, limite raggiunto, interrotto, con messaggi e azioni |
| `TribunalPhaseIndicator` | `TribunalPhaseIndicator.tsx` | `Stepper` a 4 passi: Fascicolo, Apertura, Replica, Sintesi |
| `TribunalVoices` | `TribunalVoices.tsx` | colonne (desktop) o schede (mobile) |
| `TribunalVoiceColumn` | `TribunalVoiceColumn.tsx` | intestazione voce (nome, mandato, stato), elenco argomenti |
| `TribunalArgumentCard` | `TribunalArgumentCard.tsx` | badge posizione, tema, testo con fatti, repliche ricevute |
| `TribunalRebuttalCard` | `TribunalRebuttalCard.tsx` | replica annidata sotto l'argomento a cui risponde |
| `TribunalRichText` | `TribunalRichText.tsx` | rende `text_template` con i segnaposto come chip (§3.1) |
| `TribunalFactChip`, `TribunalFactDetails` | `TribunalFactChip.tsx` | chip selezionabile e dettaglio del fatto (popover / bottom sheet) |
| `TribunalSynthesis` | `TribunalSynthesis.tsx` | punti condivisi, punti contesi con i lati, domande aperte |
| `TribunalDiscardedNotice` | `TribunalDiscardedNotice.tsx` | conteggio degli scartati con spiegazione (§6.6) |
| `TribunalCaseFilePanel` | `TribunalCaseFilePanel.tsx` | accordion con tutti i fatti del fascicolo per gruppo |
| formattazione e copy | `tribunalFormat.ts` | etichette italiane (§6), colori delle voci (§11), maschera Privacy (§8), `splitTemplate(template)` |
| test | `Tribunal.test.tsx` | Vitest sui componenti (§13) |

`TribunalContestedActions.tsx` è di TASK-70 (§9); `useTribunalSession.ts` e `fixtures/` di TASK-67.

### 3.1 Testo con fatti selezionabili

- Il testo si rende sempre da `text_template` (o `summary_template`): `splitTemplate` divide sulla
  regex `\{F([1-9][0-9]{0,2})\}`; ogni segnaposto diventa un `TribunalFactChip` che mostra il
  `formatted` del fatto (o la maschera, §8), il resto è testo semplice (nessun Markdown, nessun
  HTML: React lo inserisce come testo).
- Sotto il testo, i fatti di `fact_ids` che non compaiono come segnaposto sono elencati come chip
  piccoli dopo la parola «Fonti:».
- Se un segnaposto punta a un fatto assente (non dovrebbe accadere) si mostra il `text` finale
  senza chip.
- `TribunalFactDetails` mostra: etichetta (`label`), valore (`formatted`), fonte (§6.5), qualità
  (badge §6.4 con icona e testo), `reason` se presente, `subject` se presente, id del fatto
  (piccolo, grigio). Su desktop è un `Popover` ancorato al chip (chiusura con Esc e clic fuori),
  su mobile un `BottomSheet`.

### 3.2 Argomento e repliche

- Card con bordo sinistro del colore della voce; in alto il badge della posizione (§6.2, icona +
  testo) e il tema (§6.3) come testo secondario; poi il testo.
- Le repliche ricevute sono annidate **sotto l'argomento bersaglio**, nella colonna della voce
  bersaglio, rientrate, con bordo sinistro del colore della voce che replica e intestazione
  «Replica <di + voce> · <Concorda|Contesta|Precisa>» con la preposizione articolata («Replica
  del fattoriale», «Replica dell'indicizzatore»).
- Nella colonna della voce che replica compare una riga compatta «Ha replicato <a + voce>»
  («Ha replicato al prudente», «Ha replicato all'indicizzatore»)
  che porta all'argomento bersaglio (scroll e focus; su mobile cambia anche scheda). Ogni card ha
  `id="tribunal-<id elemento>"`.
- Durante la fase di apertura una voce in attesa mostra due `Skeleton`; durante la replica le
  repliche in arrivo compaiono sotto i loro bersagli senza spostare il resto della pagina oltre il
  necessario.

### 3.3 Sintesi

- **Punti condivisi**: elenco; per ciascuno il testo e i nomi delle voci (`voices`) come badge
  neutri «Concordano: L'indicizzatore, Il prudente».
- **Punti contesi**: card con il testo della questione; sotto, i due lati affiancati, ciascuno
  con i nomi delle voci (badge col colore della voce) e il `summary`; collegamenti agli argomenti
  citati (`argument_ids`, scroll e focus). In fondo alla card lo slot `renderContestedActions`.
- **Domande aperte**: elenco numerato dal browser (`<ol>`), introdotto da «Domande per te».
- Sintesi con le tre liste vuote: «La sintesi non ha prodotto punti verificabili. Gli argomenti
  delle voci restano consultabili qui sopra.»

## 4. Stati

L'elemento radice di `TribunalSection` ha `data-state` (e `data-phase` durante `running`), come
le sezioni del Doctor 2.0, per test ed E2E.

| `data-state` | quando | resa |
|---|---|---|
| `loading` | features, stato o ultima seduta in caricamento | `Skeleton` della sezione + avvertenza |
| `unavailable` | `status.available = false` con `reason` `copilot_not_configured` o `provider_not_supported` | messaggio (§4.1) + pulsante «Apri Impostazioni» (`navigate('/settings')`; il testo indica «Impostazioni → Copilot» perché la scheda non ha deep link). Se esiste una seduta salvata, la si mostra sotto in sola lettura |
| `ready` | disponibile e nessuna seduta salvata (o seduta scartata dall'utente) | introduzione, le tre voci con nome e mandato, «Avvia la seduta»; con `key_source = "server"` la riga «Sedute disponibili oggi: X di N»; in piccolo «Usa il Copilot configurato (<provider> · <model>)» |
| `running` (`data-phase` = `apertura` \| `replica` \| `sintesi`) | stream aperto | indicatore di fase, colonne che si riempiono, pulsante «Interrompi» (chiude la connessione) |
| `completed` | evento `done`, oppure seduta salvata caricata con `loadSaved` | seduta completa; se salvata: «Seduta del <data e ora locali>» (`created_at`), e con `data_changed = true` l'avviso giallo «I dati del portafoglio sono cambiati da questa seduta: alcuni valori potrebbero non essere più attuali.» Azione «Rifai la seduta» (`redo`, `force_new: true`), con la nota «Usa una delle sedute di oggi» se `key_source = "server"`. `data-source="saved"` o `"live"` |
| `error` | errore HTTP prima dello stream o evento `error` | `Alert` rosso con il messaggio (§4.1) e «Riprova» se `retryable`; tutto ciò che era già arrivato resta visibile sotto, con la nota «Seduta incompleta: non è stata salvata.» |
| `limit_reached` | `status.reason = "daily_limit_reached"` all'apertura, oppure 429 `daily_limit_reached` all'avvio | messaggio con l'ora di ripristino (§4.1); «Avvia la seduta» disabilitato; la seduta salvata, se c'è, resta visibile sotto |
| `aborted` | l'utente ha premuto «Interrompi» | «Seduta interrotta: non è stata salvata.» + «Avvia la seduta»; il contenuto arrivato resta visibile |

Comportamento all'apertura della sezione: si caricano stato e ultima seduta; se c'è una seduta
salvata la si mostra subito (`completed`, `data-source="saved"`), altrimenti `ready` /
`unavailable` / `limit_reached`. «Avvia la seduta» con fascicolo invariato restituisce la seduta
salvata (riproduzione, `reused: true`): l'interfaccia la mostra come conclusa con la data della
seduta originale. Il frontend non decide il riuso: lo decide il backend.

Durante `running`, una voce con `voice_error` mostra nella sua colonna il messaggio dell'errore
(§4.1) al posto degli argomenti; una voce con `admitted: 0` mostra «Nessun argomento ha superato
la verifica.».

### 4.1 Messaggi

Il frontend usa questi testi in base al codice; il `message` del backend serve solo per codici
sconosciuti.

| codice | testo |
|---|---|
| `copilot_not_configured`, `copilot_unavailable` | «Il Tribunale usa il Copilot, che non è ancora configurato. Aggiungi una chiave API in Impostazioni → Copilot.» |
| `provider_not_supported` | «Il modello configurato non supporta le risposte strutturate richieste dal Tribunale. In Impostazioni → Copilot scegli OpenAI, Anthropic, Gemini oppure OpenRouter.» |
| `daily_limit_reached` | «Hai usato tutte le sedute di oggi disponibili con la chiave del server. Potrai avviarne un'altra dalle <HH:MM di resets_at in ora locale>. Con una tua chiave API, in Impostazioni → Copilot, non ci sono limiti giornalieri.» |
| `session_in_progress` | «C'è già una seduta in corso. Attendi che finisca prima di avviarne un'altra.» |
| `empty_portfolio` | «Il portafoglio non ha posizioni investite: non c'è ancora nulla da discutere.» |
| `insufficient_data` | «Il Doctor non ha abbastanza dati affidabili per una seduta. Aggiorna le quotazioni o completa i dati degli strumenti e riprova.» |
| `not_found` | «Portafoglio non trovato.» |
| `invalid_request` | «Selezione dei portafogli non valida.» |
| `timeout` | «La seduta ha impiegato troppo tempo ed è stata interrotta.» |
| `too_few_voices` | «Meno di due voci hanno prodotto argomenti verificabili: la seduta si è fermata. Riprova tra poco.» |
| `synthesis_failed` | «La sintesi non è riuscita. Gli argomenti delle voci restano visibili.» |
| `internal_error` | «Errore imprevisto durante la seduta.» |
| `stream_interrupted` | «La connessione si è interrotta prima della fine della seduta.» |
| `network_error` | «Connessione interrotta prima della risposta. Controlla la rete e riprova.» |
| `voice_error` `timeout` | «<Nome voce> non ha risposto in tempo: la seduta prosegue con le altre voci.» |
| `voice_error` `schema_mismatch` | «<Nome voce> ha risposto in un formato non valido: la seduta prosegue con le altre voci.» |
| `voice_error` `provider_error` / `unsupported_provider` | «<Nome voce> non è disponibile per un errore del servizio AI: la seduta prosegue con le altre voci.» |
| `feature_disabled` | nessun messaggio: la sezione non viene mostrata |

## 5. Avvertenza

Sempre visibile in cima alla sezione, in tutti gli stati (anche `loading`, `unavailable` ed
`error`), come `Alert` informativo (`variant="light"`, icona `IconInfoCircle`), non chiudibile.
Testo esatto:

> Il Tribunale mette a confronto tre letture automatiche del tuo portafoglio, ciascuna con un
> punto di vista dichiarato. Ogni numero viene dai calcoli del Doctor; i testi sono generati da
> un modello di intelligenza artificiale e possono essere incompleti. Non è una consulenza
> finanziaria personalizzata: non indica cosa comprare o vendere e non valuta se il portafoglio è
> adatto a te. Le scelte restano tue.

Su mobile la prima frase e l'ultima restano visibili e il resto si espande con «Leggi tutto»
(il testo completo è nel DOM, `aria-expanded` sul pulsante).

## 6. Etichette e copy

### 6.1 Voci

| id | nome | scheda mobile | colore Mantine | mandato mostrato |
|---|---|---|---|---|
| `indicizzatore` | L'indicizzatore | Indicizzatore | `blue` | `VoiceInfo.mandate` |
| `fattoriale` | Il fattoriale | Fattoriale | `grape` | idem |
| `prudente` | Il prudente | Prudente | `orange` | idem |

Il nome della voce è sempre scritto accanto al colore (mai colore da solo).

### 6.2 Posizioni

| `stance` | etichetta | icona | colore |
|---|---|---|---|
| `punto_di_forza` | Punto di forza | `IconCircleCheck` | `green` (light) |
| `criticita` | Criticità | `IconAlertTriangle` | `red` (light) |
| `neutro` | Osservazione | `IconCircleDot` | `gray` (light) |
| `concorda` (replica) | Concorda | `IconThumbUp` | `gray` (outline) |
| `contesta` (replica) | Contesta | `IconArrowsExchange` | `gray` (outline) |
| `precisa` (replica) | Precisa | `IconInfoCircle` | `gray` (outline) |

### 6.3 Temi

`costi` Costi · `diversificazione` Diversificazione · `concentrazione` Concentrazione ·
`composizione` Composizione · `esposizione_geografica` Esposizione geografica ·
`esposizione_settoriale` Esposizione settoriale · `rischio` Rischio · `scenari` Scenari ·
`regole_personali` I miei parametri · `qualita_dati` Qualità dei dati.

### 6.4 Qualità del dato

`ok` «Dato completo» (icona check, verde) · `partial` «Dato parziale» (giallo) · `stale` «Quotazioni
non aggiornate» (giallo) · `missing` «Dato mancante» (grigio). Un fatto `citable: false` mostra in
più «Non citabile» e il `reason`.

### 6.5 Fonti

`doctor_metrics` «Metriche del Doctor» · `positions` «Posizioni del portafoglio» ·
`health_score` «Punteggio di salute» · `health_alerts` «Avvisi del Doctor» · `xray` «X-Ray
(look-through)» · `stress_test` «Stress test storici» · `monte_carlo` «Simulazione Monte Carlo» ·
`doctor_policy` «I miei parametri».

### 6.6 Argomenti scartati

`TribunalDiscardedNotice`, sotto la sintesi (e durante la seduta sotto le colonne), visibile solo
se `discarded.total > 0`:

- titolo: «<N> affermazioni scartate dal controllo automatico» (singolare «1 affermazione
  scartata …»);
- spiegazione: «Prima di mostrarti una frase, il Tribunale controlla che ogni numero venga dai
  dati del Doctor, che non nomini strumenti fuori dal tuo portafoglio e che non contenga
  indicazioni di acquisto o vendita. Le frasi che non superano il controllo non vengono mostrate:
  qui vedi solo quante sono e perché.»;
- dettaglio espandibile: conteggi per voce («L'indicizzatore: 1», …, «Sintesi: 1») e per motivo,
  con queste etichette:

| codice | motivo mostrato |
|---|---|
| `schema_non_valido` | risposta incompleta o malformata |
| `riferimento_non_ammesso` | risposta a un argomento non valido |
| `nessun_fatto` | nessun dato del Doctor citato |
| `troppi_fatti` | troppi dati citati insieme |
| `fatto_inesistente` | dato citato che non esiste |
| `fatto_non_citabile` | dato mancante o non aggiornato |
| `segnaposto_malformato` | riferimento a un dato scritto male |
| `segnaposto_non_citato` | valore non dichiarato tra le fonti |
| `fatto_estraneo` | dato non usato dalle voci richiamate |
| `testo_troppo_lungo` | testo troppo lungo |
| `strumento_non_ammesso` | strumento non presente nel portafoglio |
| `cifra_libera` | numero scritto senza prenderlo dai dati |
| `indicazione_operativa` | indicazione di acquisto, vendita o consiglio |
| `verdetto` | giudizio su chi ha ragione |
| `troppi_argomenti` | oltre il numero massimo di argomenti |

Il testo degli scartati non arriva mai al frontend: non c'è nulla da «mostrare comunque».

### 6.7 Regole di forma

Tono fattuale, italiano semplice, «le voci» al plurale. Date in formato italiano
(«10 novembre 2026, 15:03», ora locale). Nessun termine vietato dal D09 del Doctor 2.0 nei testi
dell'interfaccia (`adeguat`, `mifid`, `consigli`, `raccomand`, `pericolos`, `dovresti`, `devi `).

## 7. Nessun vincitore

L'interfaccia non deve suggerire che una voce abbia ragione:

- colonne di uguale larghezza, ordine fisso, stessi stili; nessuna voce evidenziata;
- nessun punteggio, conteggio comparativo («3 punti di forza contro 1»), classifica, percentuale
  di accordo, trofeo, spunta o colore «vincente» su voci o lati;
- nei punti contesi i due lati hanno lo stesso peso visivo, nell'ordine dato dal backend;
- il riepilogo finale parla di «punti condivisi», «punti contesi» e «domande per te», mai di
  «esito», «verdetto» o «conclusione»;
- l'intestazione delle voci mostra solo il numero dei propri argomenti, senza confronti; gli
  scartati per voce stanno solo nel dettaglio di §6.6.

## 8. Privacy Mode

Letta come nel resto del Doctor (`STORAGE_KEYS.privacyModeEnabled`, prop `privacy` passata dalla
pagina).

- Il fascicolo **non contiene importi** in valuta (contratto §4.1): percentuali, mesi, indici e
  conteggi restano visibili, come in «I miei parametri».
- I fatti con `sensitive: true` (il punteggio di salute, `unit = "score"`) sono mascherati con
  `******` ovunque: nei chip del testo (per questo il testo si rende sempre da `text_template`,
  mai da `text`), nel dettaglio del fatto, nell'elenco del fascicolo. Coerente con la Diagnosi,
  che maschera lo score.
- Rete di sicurezza: `maskMoneyInText` (`components/doctor/policy/policyFormat.ts`) è applicato
  alle parti di testo libero (tra i chip), alle `reason` e ai messaggi di errore, nel caso un
  importo con valuta finisse in un testo.
- Il prompt precompilato per il Copilot (§9) omette i fatti `sensitive` quando la Privacy Mode è
  attiva.
- Nessuna funzione di condivisione o esportazione della seduta.

## 9. Dalle divergenze all'azione (TASK-70)

Per ogni punto conteso, nello slot `renderContestedActions`, `TribunalContestedActions` mostra
fino a tre pulsanti secondari (`variant="light"`, `size="xs"`), solo se la destinazione è
disponibile:

| azione | etichetta | visibile se | effetto |
|---|---|---|---|
| Copilot | «Approfondisci con il Copilot» | Copilot disponibile (`getCopilotStatus`) | apre il Copilot con la domanda precompilata (sotto), tramite `handleAskCopilot` della pagina |
| I miei parametri | «Fissa un tuo parametro» | `features.policyEnabled` e `point.metric_codes.length > 0` | apre `?section=parametri` con l'editor su una **nuova regola** per `metric_codes[0]` (scelta tra i codici se più di uno), **senza soglie** precompilate; nulla viene salvato senza il flusso di conferma esistente |
| Laboratorio | «Prova uno scenario» | `features.simulatorEnabled` | apre `?section=laboratorio` senza precompilare operazioni o pesi |

In vista aggregata le tre azioni valgono allo stesso modo (i parametri aggregati sono
indipendenti da quelli dei singoli portafogli e il Laboratorio lavora sui pesi complessivi);
nell'editor e nel Laboratorio resta l'avviso di scope già esistente.

Domanda precompilata (`buildContestedCopilotPrompt`), una riga per elemento:

```
Nel Tribunale del portafoglio le voci non concordano su questo punto: «<point.text>».
Dati citati: <label>: <formatted>; <label>: <formatted>.
<nome voci lato 1>: «<summary lato 1>»
<nome voci lato 2>: «<summary lato 2>»
Aiutami a capire cosa misurano questi dati e quali domande pormi. Nessuna indicazione di acquisto o vendita.
```

«Dati citati» elenca i fatti di `point.fact_ids` e dei lati, senza duplicati, nell'ordine di
apparizione (fatti `sensitive` omessi con la Privacy Mode attiva). Nessuna azione propone
strumenti, importi o soglie.

## 10. Accessibilità

- Regione `aria-live="polite"` che annuncia i cambi di fase («Apertura in corso», «Replica in
  corso», «Sintesi pronta») e la fine della seduta; non annuncia ogni singolo argomento.
- Chip dei fatti: `<button>` con `aria-label` «Dato <id>: <label>, <formatted o "nascosto">. Apri i
  dettagli»; dettaglio raggiungibile da tastiera, Esc chiude e riporta il focus al chip.
- Posizioni e qualità mai solo a colori (icona + testo); colonne con `role="region"` e
  `aria-label` col nome della voce; schede mobili con i ruoli `tablist`/`tab` di Mantine.
- Le repliche hanno `aria-describedby` verso l'argomento bersaglio; i collegamenti «Ha replicato
  al/all' …» e quelli della sintesi spostano il focus sull'elemento.
- Stepper delle fasi con `aria-current="step"` sulla fase in corso.

## 11. Colori e temi

- Colori delle voci (`blue`, `grape`, `orange`) e delle posizioni (`green`, `red`, `gray`) da token
  Mantine (`var(--mantine-color-<colore>-6)`, `-light`, `-light-color`), **mai esadecimali**:
  restano uguali in tutti i temi, come i colori semantici (TASK-59), e leggibili in chiaro e in
  scuro.
- Gli elementi di marca (pulsante principale, step attivo, tab attiva) usano il colore primario
  del tema (`teal`, che `colorTheme.ts` sostituisce con il tema scelto su mobile): con un tema
  diverso da Petrolio nulla resta color petrolio.
- Nessuna voce usa `teal` per non confondersi con la marca.

## 12. Feature flag

| livello | flag | default | effetto |
|---|---|---|---|
| backend | `DOCTOR_TRIBUNAL_ENABLED` | `true` | `false`: endpoint 404 `feature_disabled`, `tribunal_enabled: false` in `/doctor/features` |
| frontend | `DOCTOR_TRIBUNAL_UI_ENABLED` (`src/features.ts`) | `true` | kill switch della sezione |

La sezione è visibile solo se entrambi sono attivi (cache 5 minuti di `/doctor/features`,
condivisa con le altre sezioni). Con il flag spento spariscono la tab e il deep link ricade su
Diagnosi, senza stati di errore.

## 13. Test attesi

- TASK-67: reducer su `tribunalEventsFixture` (stato finale uguale a `sessionToState(fixture)`
  a parte `reused`/`status`), errore a metà (stream troncato dopo l'apertura → `error`
  `stream_interrupted`, argomenti conservati), interruzione (`stop` → `aborted`, fetch annullato),
  evento sconosciuto e JSON malformato ignorati, 429 `daily_limit_reached` → `limit_reached` con
  `resetsAt`, cambio di scope → abort.
- TASK-68: ogni `data-state` (e `data-phase`), apertura del dettaglio di un fatto (popover su
  desktop, bottom sheet su mobile), repliche sotto il bersaglio, sintesi senza elementi
  «vincenti», avvertenza in tutti gli stati, Privacy Mode (score mascherato, percentuali visibili),
  conteggio degli scartati, resa mobile (schede, nessun overflow orizzontale).
- TASK-69: tab visibile con flag attivo e assente con flag spento, cambio di scope che azzera la
  sezione, vista aggregata, Copilot non configurato (`unavailable` con rimando a Impostazioni),
  endpoint «latest» assente senza errori, navigazione 2×2 su mobile senza testo troncato.
- TASK-70: le tre azioni, sezioni spente, vista aggregata, prompt senza strumenti né soglie.
