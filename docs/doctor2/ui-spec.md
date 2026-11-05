# Doctor 2.0 — Specifica UI (Diagnosi, I miei parametri, Laboratorio)

Stato: **descrizione dell'implementazione** sul branch `claude/doctor-2-policy-engine`.
Riferimenti: PRD "Valore365 — Portfolio Doctor 2.0" v1.0 (4 nov 2026), contratti
`docs/doctor2/api-contracts.md`, architettura `docs/doctor2/architecture.md`,
metodologia `docs/doctor2/financial-methodology.md`, decisioni aperte
`docs/doctor2/open-decisions.md`.

Questo documento descrive **ciò che il codice fa oggi**. Dove l'implementazione si
discosta dal PRD o dal contratto, il punto è segnalato con **Deviazione**.

Principi UI (dal contratto):

- Il frontend **non calcola nulla di finanziario**: ogni numero arriva dal backend e
  viene solo formattato (`policyFormat.ts`, `labFormat.ts`).
- Il punteggio Doctor (Health Score) e la verifica dei parametri personali restano
  **due cose separate**: non vengono mai fusi in un solo numero.
- Nessun salvataggio senza conferma esplicita dell'utente (token monouso lato server).
- Il Laboratorio non scrive mai su transazioni o posizioni.

---

## 1. Information architecture

Pagina: `src/frontend/valore-frontend/src/pages/Doctor.page.tsx` (route `/doctor`).

| sezione | valore `?section=` | contenuto | visibile se |
|---|---|---|---|
| **Diagnosi** | assente (default) | referto Doctor esistente (score, segnali, metriche, glossario, X-Ray, Monte Carlo, stress test) + card riassuntiva «I miei parametri» | sempre |
| **I miei parametri** | `parametri` | regole personali con stato, evidenze, editor, versioni e audit | flag policy attivo (§14) |
| **Laboratorio** | `laboratorio` | scenari ipotetici a confronto con il portafoglio attuale | flag simulatore attivo (§14) |

Deep link:

- `/doctor?section=parametri` e `/doctor?section=laboratorio` aprono direttamente la
  sezione. Un valore sconosciuto o una sezione disattivata dal flag ricadono su
  **Diagnosi** (nessun errore).
- Il cambio di tab aggiorna la query string con `setSearchParams` (gli altri parametri
  restano); tornando a Diagnosi il parametro `section` viene rimosso.
- Le tab (`Tabs` Mantine, `keepMounted={false}`) compaiono solo se è disponibile più di
  una sezione; su mobile occupano tutta la larghezza (`grow`).
- Ogni sezione è avvolta in `DoctorSectionErrorBoundary` con chiave legata allo scope:
  un errore di rendering in una sezione non blocca le altre e cambiando portafoglio la
  sezione riparte da zero.

Scope: il selettore `PortfolioSwitcher` (in alto, con `allowAggregate`) sceglie un
portafoglio o una vista aggregata. Policy ed evaluation sono legate allo **scope esatto**
(fingerprint `p:<id ordinati>`): la vista aggregata ha parametri propri, indipendenti da
quelli dei singoli portafogli.

Passaggi fra sezioni:

- card «I miei parametri» in Diagnosi → «Vedi i dettagli» / «Imposta i tuoi parametri»
  apre `?section=parametri`;
- evidenza di una regola → «Simula» apre `?section=laboratorio` con lo scenario
  precompilato dalla regola;
- evidenza di una regola → «Spiega» e Laboratorio → «Chiedi al Copilot di commentare»
  aprono il Copilot con un prompt già scritto.

**Deviazione**: lo stato dell'editor, del drawer evidenze e dello storico versioni non è
deep-linkabile (solo la sezione lo è).

## 2. Layout e Copilot responsive

Breakpoint (`useMediaQuery` nella pagina):

| dispositivo | condizione | Copilot (`CopilotChat` `layout`) |
|---|---|---|
| desktop | `min-width: 75em` (Mantine `lg`) | **side panel**: colonna fissa di 380 px a destra del contenuto, `position: sticky`, alta quanto il viewport; nessun overlay, la pagina resta utilizzabile |
| tablet | fra 48em e 75em | **drawer** a destra (`drawerSize="md"`) |
| mobile | `max-width: 48em` | **bottom sheet** (`components/mobile/BottomSheet`, altezza 75dvh) |

- Il pulsante flottante «Apri Doctor Copilot» (icona robot, `aria-label`) è visibile se il
  Copilot è disponibile (`getCopilotStatus`) e il side panel non è già aperto; su mobile
  è alzato sopra la bottom navigation (`92px + safe area`).
- Il side panel è un `<aside aria-label="Doctor Copilot">` con pulsante di chiusura.
- Quando lo scope è aggregato il Copilot riceve `portfolioIds` (tutti gli id) e
  `portfolioId` = primo id; i tool Doctor usano sempre lo scope deciso dal backend, mai
  quello del LLM.

Layout delle sezioni:

- **Diagnosi**: griglia esistente. La card «I miei parametri» sta nella colonna destra
  (`xl: 4/12`), sopra «Segnali principali»; su schermi stretti va sotto il punteggio.
- **I miei parametri**: card intestazione → avvisi → lista regole in griglia
  (`SimpleGrid` 1 colonna su mobile, 2 da `md`) → storico versioni (se aperto).
- **Editor**: `Modal` `size="xl"` su desktop/tablet, **a schermo intero** su mobile.
- **Evidenze**: `Drawer` a destra (`size="md"`) su desktop/tablet, **bottom sheet** su mobile.
- **Laboratorio**: builder degli scenari impilati; risultati con tabella di confronto su
  desktop/tablet e **card impilate** su mobile (§11, §12).

Indicatore di freschezza (`FreshnessIndicator`): se esiste un'evaluation valida è
mostrato sotto le tab, in tutte e tre le sezioni (badge con tooltip + data dell'ultima
sincronizzazione + simboli con quote ferme o mancanti, max 6 elencati).

## 3. Mappa dei componenti

Percorsi relativi a `src/frontend/valore-frontend/src/`.

### 3.1 Componenti esistenti riusati

| componente | file | uso in Doctor 2.0 |
|---|---|---|
| `DoctorPage` | `pages/Doctor.page.tsx` | contenitore; tab, deep link, layout Copilot, collegamenti fra sezioni |
| `PortfolioSwitcher` | `components/portfolio/PortfolioSwitcher.tsx` | scelta scope singolo/aggregato |
| `AggregateScopeNotice` | `scope/AggregateReadOnly.tsx` | avviso vista aggregata (Diagnosi) |
| `DoctorScoreCard`, `XRayCard`, `MonteCarloCard`, `StressTestCard`, `DoctorAlertDetailsModal`, `GlossaryTooltip` | `components/doctor/*` | referto Diagnosi invariato |
| `DoctorSectionErrorBoundary` | `components/doctor/DoctorSectionErrorBoundary.tsx` | isolamento errori per sezione |
| `CopilotChat` | `components/copilot/CopilotChat.tsx` | esteso con `layout` (`side-panel` / `drawer` / `bottom-sheet`), evento SSE `policy_draft`, callback `onPolicySaved` |
| `BottomSheet` | `components/mobile/BottomSheet.tsx` | evidenze, Copilot e glossario su mobile |
| `PageLayout`, `PageHeader` | `components/layout/*` | struttura pagina |
| `usePortfolioPositions` | `components/dashboard/hooks/queries.ts` | elenco strumenti nel builder del Laboratorio |

### 3.2 Componenti nuovi — «I miei parametri» (`components/doctor/policy/`)

| componente / modulo | file | responsabilità |
|---|---|---|
| `DoctorPolicySummaryCard` | `DoctorPolicySummaryCard.tsx` | card in Diagnosi: conformità sintetica, prima violazione, avviso quote ferme |
| `DoctorParametriSection` | `DoctorParametriSection.tsx` | sezione «I miei parametri»: intestazione, stati, lista, drawer, editor, versioni |
| `DoctorPolicyRulesList`, `PolicyRuleCard` | `DoctorPolicyRulesList.tsx` | riepilogo + card di ogni regola nell'ordine del backend |
| `RuleStatusBadge`, `QualityBadge` | `RuleStatusBadge.tsx` | stato regola e qualità dato con icona + testo |
| `FreshnessIndicator` | `FreshnessIndicator.tsx` | freschezza quote (`data_quality`) |
| `PolicyEvidenceDrawer`, `PolicyEvidenceBody` | `PolicyEvidenceDrawer.tsx` | evidenze di una regola e azioni Spiega / Simula / Modifica |
| `DoctorPolicyRuleEditor` | `DoctorPolicyRuleEditor.tsx` | editor: validate → preview → conferma → save |
| `PolicyPreviewSummary`, `PolicyDiffList`, `describeScope` | `PolicyPreviewSummary.tsx` | diff e conformità prima/dopo (editor, card Copilot, storico) |
| `PolicyVersionHistory` | `PolicyVersionHistory.tsx` | versioni, fonte, diff e ripristino |
| `PolicyDraftCard`, `parsePolicyDraft` | `PolicyDraftCard.tsx` | card della bozza proposta dal Copilot |
| hook React Query | `hooks.ts` | `useDoctorFeatures`, `useDoctorMetrics`, `useDoctorTemplates`, `useDoctorPolicyState`, `useDoctorPolicyVersions`, `useInvalidateDoctorPolicy` |
| formattazione e copy | `policyFormat.ts` | numeri in italiano, etichette stato, messaggi di errore, maschera Privacy |
| test | `DoctorPolicy.test.tsx`, `testFixtures.ts` | test Vitest dei componenti |

### 3.3 Componenti nuovi — «Laboratorio» (`components/doctor/lab/`)

| componente / modulo | file | responsabilità |
|---|---|---|
| `DoctorLabSection` | `DoctorLabSection.tsx` | sezione Laboratorio: scenari (max 3), esecuzione, risultati, link Copilot/Portfolio/FIRE |
| `ScenarioBuilder` | `ScenarioBuilder.tsx` | input di uno scenario (modalità, liquidità, operazioni, pesi, vincoli, commissioni) |
| `ScenarioFeasibilitySummary` | `ScenarioFeasibilitySummary.tsx` | fattibile / non fattibile con motivo, importi (mascherati in Privacy Mode) |
| `ScenarioComparisonTable` | `ScenarioComparisonTable.tsx` | «Attuale» vs scenari: tabella (desktop) o card (mobile) |
| `ScenarioTradeoffs` | `ScenarioTradeoffs.tsx` | regole risolte, nuove violazioni, avvertenze, variazioni per posizione |
| formattazione | `labFormat.ts` | `emptyScenario`, `formatMetric`, `isIncomplete`, `touchedMetrics` |
| test | `DoctorLab.test.tsx` | test Vitest |

### 3.4 Servizi e flag

| modulo | file |
|---|---|
| client API Doctor 2.0 | `services/api/doctor.ts` (`getDoctorFeatures`, `getDoctorMetrics`, `getDoctorTemplates`, `getDoctorPolicy`, `getDoctorEvaluation`, `validateDoctorPolicy`, `previewDoctorPolicy`, `saveDoctorPolicy`, `getDoctorPolicyVersions`, `restoreDoctorPolicyVersion`, `previewDoctorScenario`, `compareDoctorScenarios`, `doctorScopeFingerprint`) |
| tipi | `services/api/types.ts` (`DoctorPolicy*`, `DoctorRuleResult`, `DoctorScenario*`) |
| kill switch frontend | `features.ts` (`DOCTOR_POLICY_UI_ENABLED`, `DOCTOR_LAB_UI_ENABLED`) |

Chiavi React Query (`doctorQueryKeys`): `doctor-features`, `doctor-metrics`,
`doctor-templates`, `['doctor-policy', fingerprint]`,
`['doctor-evaluation', fingerprint, policyVersion]`,
`['doctor-policy-versions', policyId, policyVersion]`. La chiave dell'evaluation include la
versione della policy, così dopo un salvataggio non si vede mai un risultato calcolato
sulla versione precedente. Gli errori 4xx (404 `feature_disabled`, 409, 422) non vengono
ritentati; i 5xx fino a 2 volte.

## 4. Stati UI

Ogni stato è marcato nel DOM con `data-state` (utile per test ed E2E).

| stato | quando | resa (card Diagnosi / sezione parametri) |
|---|---|---|
| `loading` | policy o evaluation in caricamento | card: loader + «Verifica dei tuoi parametri…»; sezione: loader centrato |
| `ready` | evaluation `status = "ready"` | card: riepilogo «4 rispettati · 1 violato · 1 non verificabile», eventuale «di cui N vicini al limite», motivo della prima regola violata, «Vedi i dettagli»; sezione: lista regole |
| `warning` | regole violate (`FAIL`) o dati parziali | **Deviazione**: il codice non ha uno stato `warning` dedicato. Una regola `FAIL` è «Violato» (rosso, icona X); la qualità `partial` è il badge «Dati parziali» (giallo); `data_quality.status = partial` dà il badge di freschezza «Dati parziali» |
| `near_limit` | regola `PASS` con `near_limit = true` | badge «Vicino al limite» (giallo, icona triangolo); conteggiata fra i rispettati e richiamata da «di cui N vicini al limite». Mai presentata come violazione |
| `unknown` | regola `UNKNOWN` | badge «Non verificabile» (grigio, icona punto interrogativo); il valore mostra i bounds («tra 35,0% e 65,0%») o «N/D», mai uno 0 inventato. Con quota non classificata (asset class, USA) decidono solo i bounds: se l'intervallo attraversa la soglia la regola resta non verificabile anche con copertura sopra il minimo. Il riepilogo elenca sempre i non verificabili (mai «5/6 rispettati») |
| `stale` | `data_quality.status = "stale"` | card: badge arancione «Quotazioni non aggiornate: alcune regole non sono verificabili»; indicatore freschezza arancione con elenco simboli; le regole interessate sono `UNKNOWN` (il backend non dà mai PASS su dati stale) e mostrano il badge qualità «Dati non aggiornati» |
| `error` | errore di rete/API su policy o evaluation | card: avviso rosso «Non riusciamo a verificare i tuoi parametri ora.» + messaggio; sezione: «Non riusciamo a caricare i tuoi parametri.» + pulsante **Riprova** (invalida le query dello scope) |
| `no_policy` | evaluation `status = "no_policy"` | card: «Non hai ancora impostato parametri per questo ambito.» + «Imposta i tuoi parametri»; sezione: «Nessun parametro per questo ambito» + «Parti da regole vuote» / «Parti da un modello illustrativo» |
| `empty_portfolio` | evaluation `status = "empty_portfolio"` | card: «Nessuna posizione: i parametri si verificano dopo le prime transazioni.»; sezione: avviso grigio, regole non applicabili |
| `aggregate_scope` | vista aggregata | card: riga con icona pila «<nome scope>: parametri indipendenti da quelli dei singoli portafogli.»; sezione: avviso «Questi parametri valgono solo per questa combinazione di portafogli…»; Laboratorio: «Vista aggregata: la simulazione lavora sui pesi complessivi, senza ordini per singolo conto.» |

Stati aggiuntivi presenti nel codice:

- `unavailable` (sezione parametri): né errore né evaluation valida → «Verifica dei
  parametri non disponibile al momento (N/D).». Nella card Diagnosi un corpo di risposta
  non valido è trattato come errore.
- Flag spento: la tab e la card non vengono mostrate (nessuno stato di errore).
- Errori di dominio tradotti da `doctorErrorMessage`: `version_conflict`,
  `confirmation_invalid`, `snapshot_changed` («I dati del portafoglio sono cambiati:
  riesegui la simulazione.»), `feature_disabled` («Funzione non disponibile al
  momento.»), `not_found` («Ambito non trovato: uno dei portafogli potrebbe non esistere più.»).

Stati delle regole (`ruleStatusMeta`): `FAIL` → «Violato», `UNKNOWN` → «Non
verificabile», `PASS` + near limit → «Vicino al limite», `PASS` → «Rispettato»,
`NOT_APPLICABLE` → «Non applicabile», `INACTIVE` → «Disattivato». L'ordine è quello del
backend (FAIL → UNKNOWN → near limit → PASS → NOT_APPLICABLE → INACTIVE): il frontend non
riordina.

## 5. Card regola

`PolicyRuleCard` (in `DoctorPolicyRulesList.tsx`) è un pulsante a tutta larghezza con
bordo sinistro del colore dello stato. Contenuto:

1. **Nome**: `label` della regola se presente, altrimenti etichetta della metrica dal
   registry (`/doctor/metrics`, con fallback locale `METRIC_LABELS`).
2. **Stato**: `RuleStatusBadge` (icona + testo) e chevron.
3. **Valore attuale**: valore puntuale con la `precision` della regola; se il backend dà
   solo i bounds, «tra X% e Y%»; altrimenti «N/D».
4. **Soglia**: «max 35%», «min 20%», «20,0%–40,0%».
5. **Scostamento**: `breach_amount` in punti percentuali («11,6 pp») solo per le regole
   violate, altrimenti «—».
6. **Motivo**: la frase del backend (`reason`), in rosso se violata.
7. **Metadati**: severità («Severità Alta/Media/Bassa»), copertura («Copertura 70%») e
   badge qualità (assente se `ok`).

Sopra la griglia: riepilogo di conformità (`formatComplianceSummary`).

## 6. Drawer evidenze

`PolicyEvidenceDrawer` si apre cliccando (o premendo Invio/Spazio su) una card. Titolo =
nome della regola. Contenuto (`PolicyEvidenceBody`):

- badge stato e qualità; motivo;
- griglia: Valore attuale, Soglia, Scostamento, Severità, Copertura dati, «Quote al»
  (`evidence.quote_as_of`);
- **Formula e metodologia**: descrizione della metrica dal registry; fonte
  (`evidence.source`), versione metodologia, data di calcolo;
- **Denominatore**: descrizione testuale e valore in valuta base (mascherato in Privacy Mode);
- **Strumenti che contribuiscono**: tabella Strumento (simbolo · nome) / ISIN / Peso
  (max 10 dal backend); «Nessuno strumento da evidenziare.» se vuota;
- **Note** del backend (es. quota stimata, listing aggregati, inferenza regione).

Azioni:

| azione | effetto | disabilitata se |
|---|---|---|
| **Spiega** | chiude il drawer e apre il Copilot con un prompt che cita nome ed esito della regola e chiede cosa misura, da quali strumenti dipende e quali dati mancano («Niente consulenza prescrittiva: è un mio parametro, non una raccomandazione.») | Copilot non disponibile |
| **Simula** | apre il Laboratorio con lo scenario A intitolato «Rientro: <regola>» e il motivo della regola come suggerimento | simulatore spento |
| **Modifica** | apre l'editor con la regola evidenziata (bordo blu) | — |

**Deviazione**: «Simula» precompila solo titolo e suggerimento; non imposta pesi o
importi (il calcolo del rientro, es. liquidità necessaria senza vendite, lo fa il backend
quando l'utente esegue lo scenario).

## 7. Editor: validate → preview → conferma → save

`DoctorPolicyRuleEditor` (modale; a schermo intero su mobile).

**Modifica** (titolo «Modifica i tuoi parametri»):

- Ambito mostrato in chiaro; campo **Nome** (default «I miei parametri», max 80).
- **Parti da un modello** (template illustrativi dal backend, con disclaimer «I modelli
  sono esempi illustrativi, non raccomandazioni: rivedi ogni soglia.» o quello del
  backend) e **Parti da regole vuote**.
- Una card per regola: Operatore (`SegmentedControl` Minimo/Massimo/Intervallo, solo gli
  operatori ammessi dal registry), Valore minimo/massimo (%) — mostrati in base
  all'operatore e azzerati quando non servono —, Severità, Margine di avviso (pp),
  Copertura minima (%), Età massima quote (giorni, 1–365), Etichetta, «Regola attiva»,
  pulsante Rimuovi.
- **Aggiungi una regola**: select delle metriche, quelle già usate disabilitate; max 20 regole.
- Una nuova regola parte **senza soglie** (l'utente le sceglie; nessun valore suggerito),
  con i default del contratto: precisione 1 (TER 2), severità media, margine dal registry,
  copertura 80, età 5 giorni. Svuotare «Margine di avviso», «Copertura minima» o «Età
  massima quote» invia `null` (placeholder «Predefinito della metrica» / «Predefinita (80%)»
  / «Predefinita (5 giorni)»): il backend applica il default, mai uno 0 silenzioso.
- Aperto da «Apri nell'editor» di una bozza Copilot: l'editor carica le regole e il nome
  della bozza al posto di quelli salvati, con l'avviso «Bozza del Copilot caricata…» e
  `source: "copilot"` in preview (diventa `manual` se l'utente modifica una regola); il
  flusso validate → preview → conferma resta identico.
- Nome al salvataggio: se il campo è vuoto, per una policy esistente si invia `null` (il
  backend mantiene il nome attuale), per una nuova «I miei parametri».

**Flusso**:

1. «Verifica e anteprima» → `POST /doctor/policies/validate`. Gli errori `field_errors`
   (`rules[0].max_value` …) sono mostrati sotto il campo corrispondente; quelli generali
   (es. `infeasible` «55+50+10 = 115%») in un avviso in alto. Con errori non si va avanti.
2. Documento valido → `POST /doctor/policies/preview` con il documento normalizzato,
   `base_version` = versione corrente (o `null`) e `source` (`manual`, oppure `template`
   se l'utente è partito da un modello e non ha toccato le regole).
3. **Conferma** (titolo «Conferma le modifiche»): `PolicyPreviewSummary` con ambito,
   **Modifiche** (diff: Aggiunta / Rimossa / Modificata, «max 35% → max 30%») e
   **Verifica sugli stessi dati** (Prima / Dopo, con lo stesso snapshot). Testo «Nulla
   viene salvato finché non confermi.». Pulsanti «Torna alle modifiche» e «Conferma e salva».
4. «Conferma e salva» → `POST /doctor/policies` con documento normalizzato,
   `base_version` della preview e `confirmation_token`. In caso di successo la modale si
   chiude, compare «Parametri salvati: versione N.» e vengono invalidate policy,
   evaluation e versioni dello scope.

**Errori**:

| caso | comportamento |
|---|---|
| 409 `version_conflict` (in preview o salvataggio) | avviso rosso «La policy è stata modificata in un'altra scheda: ricarica» con pulsante **Ricarica**; i pulsanti «Verifica e anteprima» / «Conferma e salva» restano disabilitati. «Ricarica» chiude l'editor e ricarica policy/evaluation/versioni (le modifiche non salvate vanno perse) |
| 409 `confirmation_invalid` (token scaduto, usato o non corrispondente) | si torna alla modifica con «La conferma non è più valida (scaduta o già usata): genera di nuovo l'anteprima e conferma.» |
| 422 `validation_error` | errori di campo inline |
| altri | messaggio da `doctorErrorMessage` |

Il token non viene mai mostrato né salvato lato client oltre lo stato della modale.

## 8. Versioni e ripristino

«Versioni e audit» (visibile solo se esiste una policy) apre `PolicyVersionHistory`:

- elenco in ordine decrescente: «Versione N», badge «Attuale», fonte (Manuale / Copilot
  (confermata da te) / Da modello / Ripristino), data di conferma, diff rispetto alla
  versione precedente;
- «Ripristina la versione N» (non sulla corrente) → modale «Ripristinare questa
  versione?» che spiega: «Le regole della versione N diventeranno una nuova versione
  (M). La cronologia resta completa.» e mostra l'**anteprima prima/dopo**:
  `POST /doctor/policies/preview` con il documento della versione N e `base_version` =
  versione corrente → diff rispetto alla versione attuale + «Verifica sugli stessi dati»
  (Prima / Dopo). Il token della preview è ignorato (il ripristino non lo richiede). Senza
  `document` nella versione o con preview in errore: «Anteprima non disponibile…», il
  ripristino resta possibile. → «Conferma ripristino» →
  `POST /doctor/policies/{id}/restore` con `base_version` = versione corrente;
- successo: «Versione ripristinata: ora è la versione M.» e invalidazione dello scope;
- 409 `version_conflict`: stesso messaggio dell'editor con «Ricarica».

**Deviazione**: l'attore non è visualizzato (il backend restituisce lo user id).

## 9. Copilot: card della bozza

1. Nella pagina Doctor (`pageContext="doctor"`) il Copilot può chiamare
   `validate_policy_draft` e `preview_policy` (mai salvare).
2. Dopo una preview valida il backend emette l'evento SSE
   `{"type": "policy_draft", "content": "<JSON>"}` con `portfolio_ids`, `draft_id`, `name`
   e la preview completa (incluso il token, che **non** arriva al LLM).
3. `CopilotChat` lo interpreta con `parsePolicyDraft` (stringa JSON o oggetto; payload
   malformato → ignorato) e aggiunge al messaggio dell'assistente una `PolicyDraftCard`.
4. La card mostra «Bozza di parametri», badge «Non ancora salvata», ambito con i **nomi**
   dei portafogli («Portafoglio Core» o «Vista aggregata: Core, Pensione»; `#id` solo se
   il nome non è noto), diff e conformità prima/dopo; se la bozza non è valida, «La bozza
   non è valida e non può essere salvata.» con gli errori.
5. **Conferma e salva** → `POST /doctor/policies` con il token della preview;
   successo → badge «Salvata», la pagina invalida le query dello scope (`onPolicySaved`).
   Il nome inviato è quello della bozza, oppure `null` (il backend mantiene il nome
   della policy esistente).
   **Annulla** → badge «Annullata», nessuna richiesta.
   **409** `version_conflict` («I parametri sono stati modificati dopo questa bozza:
   rigenera l'anteprima sulla versione attuale e conferma di nuovo.») o
   `confirmation_invalid`: «Conferma e salva» si disabilita e compare **Rigenera
   anteprima** → `GET /doctor/policies` (versione corrente) + `POST /doctor/policies/preview`
   con lo stesso documento, `base_version` corrente e `source: "copilot"`; la card mostra
   la nuova preview (nuovo token) e il salvataggio richiede di nuovo un clic esplicito.
   **Apri nell'editor** (solo nella pagina Doctor, con il flag policy attivo e se la bozza
   è dello stesso ambito della chat) → apre «I miei parametri» con l'editor precaricato
   dalla bozza (§7); nessuna richiesta di scrittura.
6. Le bozze **non vengono salvate** nella cronologia locale delle conversazioni
   (`saveCurrentConversation` conserva solo `role` e `content`): riaprendo la chat la card
   non c'è più e il token non resta in `localStorage`.

Routing del Copilot (prompt di sistema): domande su capitale, rendita, pensione, FIRE →
pagina `/fire`; ordini e target per ticker → `/portfolio`; «Vorrei 60/40» → intervalli,
domanda sull'oro e `preview_policy`.

## 10. Laboratorio

`DoctorLabSection`: fino a **3 scenari** confrontati con il portafoglio attuale.

**Costruzione** (`ScenarioBuilder`, uno per scenario, rinominabile):

| modalità | etichetta UI | input | note |
|---|---|---|---|
| `new_cash_only` (default) | Solo nuova liquidità | nuova liquidità | forza «Nessuna vendita»; i pesi massimi per strumento non sono editabili in UI, quindi il backend usa il limite della regola `max_single_position_pct` (con avvertenza) |
| `manual` | Acquisti/vendite | nuova liquidità + operazioni (strumento già posseduto, Acquisto/Vendita, importo) | **non disponibile in vista aggregata** |
| `rebalance` | Ribilanciamento | pesi obiettivo (%) per ogni posizione («complessivi» in aggregata) | posizioni non elencate ripartite pro rata dal backend |

Vincoli: «Nessuna vendita», «Mantieni invariata la quota azionaria complessiva»,
«Turnover massimo (%)», «Commissioni ipotetiche (%)» (0–10), «Commissione fissa per
operazione» (`fee_model.fixed`, 0–10.000), «Usa anche la liquidità già presente nel
portafoglio» (`constraints.use_cash_balance`, default `false`). Fiscalità: sempre
`tax_model: "none"` (D07).

**Esecuzione**: «Simula scenario» (1 scenario → `POST /doctor/scenarios/preview`) o
«Confronta scenari» (2–3 → `POST /doctor/scenarios/compare`). La richiesta include
`snapshot_id` e `policy_version` dell'evaluation corrente: se nel frattempo i dati sono
cambiati il backend risponde 409 `snapshot_changed`, la UI mostra «I dati del portafoglio
sono cambiati: riesegui la simulazione.» e ricarica l'evaluation.

**Risultati**:

- disclaimer in evidenza: «Simulazione teorica; nessun ordine eseguito.»;
- per scenario: fattibile («<nome>: fattibile — Lo scenario rispetta i vincoli indicati.»)
  o non fattibile con badge del codice (`infeasible_code`: «Liquidità insufficiente»,
  «Impossibile senza vendite», «Turnover massimo superato»…) e motivo del backend;
  «Nuova liquidità totale necessaria (senza vendite)» (`required_new_cash`) con la nota
  «È il totale minimo di nuova liquidità da versare, costi inclusi, non un'integrazione:
  confrontalo con la liquidità indicata nello scenario (<cash_in>).»; Valore prima,
  Valore dopo, Liquidità aggiunta, Costi ipotetici, Turnover (`turnover_pct`, «N/D» se nullo);
- tabella di confronto (§12) con righe Conformità, Concentrazione, Asset allocation,
  Geografia, Costi, Overlap, Rischio · Volatilità (+ righe `stress*` solo se il backend le restituisce) e marcatori
  «Migliora» / «Peggiora» / «Dati incompleti»; uno scenario non fattibile ha tutte le celle «N/D»;
- compromessi per scenario: «Regole che tornerebbero rispettate», «Nuove violazioni»,
  «Avvertenze», variazioni per posizione (in aggregata solo pesi: «Pesi complessivi
  (nessun ordine per singolo conto)»);
- piè di pagina: «Snapshot <id> · metodologia <versione>: con gli stessi dati la
  simulazione dà lo stesso risultato.»;
- azioni: «Chiedi al Copilot di commentare» (prompt che chiede di usare solo i risultati
  della simulazione, senza consulenza personalizzata) e link «Traduci in ordini nella
  pagina Portfolio» (`/portfolio`); sempre presente il link «Vai alla pagina FIRE» per
  capitale/rendita/pensione.

- in un confronto (2–3 scenari) sotto la tabella compare l'**ordinamento** del backend
  (`ranking`, `best_index`) con il titolo neutro «Ordinamento secondo i criteri:
  conformità, costi, turnover» e la nota «È un ordinamento, non una raccomandazione: con
  preferenze diverse non esiste una scelta valida per tutti.»: Posizione, Scenario,
  Fattibile, Violate dopo, Non verificabili dopo, Costi (mascherati in Privacy Mode),
  Turnover; lo scenario `best_index` ha il badge «Primo secondo questi criteri» (mai
  «soluzione migliore»). Su mobile è un elenco di card. Poi la spiegazione testuale del
  backend (`explanation`, importi mascherati in Privacy Mode);
- riga **Rischio · Volatilità**: sempre «N/D» con il motivo del backend (il Lab non stima
  la volatilità, D06).

«Costi ipotetici» mostra `costs.total` (il backend restituisce l'oggetto
`{total, variable, fixed, operations, fee_model}`); «N/D» solo se il totale è nullo.

**Deviazioni rispetto a contratto/PRD**:

- In `manual` lo strumento si sceglie per simbolo fra le posizioni dello scope; non si
  possono simulare strumenti non posseduti (limite del backend, vedi open decisions).
- La volatilità post-scenario non è stimata: la riga c'è ma vale sempre «N/D» motivato.

## 11. Accessibilità

- **Stato mai solo a colori**: `RuleStatusBadge` e `QualityBadge` hanno sempre icona
  (`aria-hidden`) + testo; i marcatori del Laboratorio sono badge con testo
  («Migliora», «Peggiora», «Dati incompleti»); la fattibilità ha titolo testuale.
- **Tastiera**: ogni card regola è un `UnstyledButton` (focus, Invio/Spazio) con
  `aria-label` «<nome>: <stato>. Apri i dettagli»; il badge di freschezza è focusabile
  (`tabIndex=0`) per leggere il tooltip; drawer, modali e bottom sheet Mantine gestiscono
  focus trap ed Esc; i `SegmentedControl` hanno `aria-labelledby`/`aria-label`; i
  pulsanti icona hanno `aria-label` (Rimuovi regola…, Rimuovi scenario…, Apri Doctor Copilot,
  Chiudi copilot); «Versioni e audit» espone `aria-expanded`.
- **Tabelle su mobile**: la tabella di confronto ha `caption`, `scope="col"` /
  `scope="row"` e, sotto 48em, diventa **card impilate** («Attuale: X → Y» per riga); su
  tablet è in `Table.ScrollContainer` (min 560 px). Le variazioni per posizione su mobile
  sono un elenco testuale. La tabella dei contributori nel drawer resta una tabella a 3
  colonne (stretta, nel bottom sheet).
- Numeri in formato italiano (`it-IT`, virgola decimale) e unità esplicite (%, pp).

## 12. Privacy Mode

La Privacy Mode è letta da `localStorage` (`STORAGE_KEYS.privacyModeEnabled`).

Regola: **gli importi assoluti in valuta sono mascherati con `******`; le percentuali
restano visibili** (sono il contenuto delle regole).

| dove | cosa viene mascherato |
|---|---|
| drawer evidenze | valore del denominatore (`formatMoney`); importi nel motivo e nelle note |
| Laboratorio | Valore prima/dopo, Liquidità aggiunta, Costi, Liquidità necessaria (anche nella nota), costi dell'ordinamento, variazioni € per posizione; importi nei testi del backend |
| Copilot (ogni pagina) | importi € nelle risposte dell'assistente (solo visualizzazione) |
| Diagnosi esistente | metriche %, punteggi per categoria e score (comportamento preesistente: qui anche le % sono mascherate) |
| testo copiato del referto (`shareSummary`) | **lo score è mascherato** («Score: ******/100»), come nella card e nell'immagine — fix di questo branch |

Testo libero e condivisione:

- Le frasi del backend possono contenere importi (es. `infeasible_reason` «mancano
  1.234,56 €», `warnings`, `explanation`). `maskMoneyInText` (`policyFormat.ts`) sostituisce
  con `******` gli importi in testo libero — «227.029 €», «€ 10.000», «1.500,50 EUR»,
  «EUR 41000», «10 euro» — lasciando visibili percentuali e numeri senza valuta. È applicato
  a: `reason` delle regole (card Diagnosi, card regola, drawer), note delle evidenze, nota
  di `data_quality` nel tooltip di freschezza, errori e messaggi della card bozza Copilot,
  suggerimento «Simula» nel Laboratorio, `infeasible_reason`, `warnings`, motivi delle
  regole risolte/nuove violazioni, motivo della volatilità, `explanation` del confronto.
- Risposte del Copilot: con Privacy Mode attiva `CopilotChat` applica `maskMoneyInText`
  ai messaggi dell'assistente su **ogni pagina**, solo in visualizzazione (la cronologia
  salvata in `localStorage` resta invariata; i messaggi dell'utente non sono toccati). Nel
  Markdown la maschera è scritta con asterischi escapati, così non diventa grassetto o
  separatore.
- Il mascheramento è un'euristica su regex: importi senza simbolo di valuta (es. «10.000»
  da solo) non vengono riconosciuti.
- Condivisione/esportazione: l'immagine del referto e il testo copiato mascherano lo
  score; il link condiviso è l'URL della pagina (nessun dato). Le sezioni «I miei
  parametri» e «Laboratorio» non hanno funzioni di condivisione/esportazione.

## 13. Linee guida di copy

Tono: fattuale, in italiano semplice, centrato su **valore misurato vs soglia scelta
dall'utente**. Le regole sono dell'utente («il tuo limite»), il Doctor verifica i dati.

Esempi (PRD / metodologia, prodotti dal backend):

- «VWRA 46,6%: supera il tuo limite 35% di 11,6 punti percentuali»
- «Quota azionaria 70,0%: supera il tuo limite 65% di 5,0 punti percentuali»
- «Quota azionaria 63,5%: entro il tuo limite 65%, a 1,5 punti percentuali dalla soglia»
- «Non possiamo verificare il limite USA: copertura insufficiente (…)»
- Riepilogo: «4 rispettati · 1 violato · 1 non verificabile» (mai «5/6 rispettati»)
- «Simulazione teorica; nessun ordine eseguito.»
- «Le regole sono tue: il Doctor verifica i dati, non indica cosa comprare o vendere.»
- Template: «Esempio illustrativo per scrivere le tue regole: non è una raccomandazione né
  una valutazione di adeguatezza.»
- Golden Lab: liquidità necessaria arrotondata per eccesso al centesimo («227.029 €»).

Regole di forma: soglie senza zeri superflui (35%, 0,25%); valori con la `precision`
della regola; «almeno» / «al massimo» quando il risultato viene dai bounds; «N/D» per i
dati mancanti, mai «0».

**Da evitare (D09)** — verificato dal test `test_doctor_policy_evaluator.py` sui testi del
backend (radici vietate: `adeguat`, `mifid`, `consigli`, `raccomand`, `pericolos`,
`dovresti`, `devi `):

- termini di adeguatezza o certificazione consulenziale («adeguato al tuo profilo»,
  «conforme MiFID», «certificato»);
- giudizi («investimento pericoloso», «portafoglio sbagliato»);
- imperativi prescrittivi («dovresti vendere», «devi ribilanciare», «ti consigliamo»);
- «compliance» / «conforme» in senso regolamentare (usare «rispettato» / «violato»).

Nota: i quick prompt preesistenti del Copilot in Diagnosi («Come ridurresti la
concentrazione…», «Dimmi un piano d azione in 30 giorni…») non sono stati rivisti con
questa lente; il test D09 copre solo i testi del motore policy.

## 14. Feature flag

| livello | flag | default | effetto |
|---|---|---|---|
| backend | `DOCTOR_POLICY_ENABLED` (`doctor_policy_enabled`) | `true` | se `false`: `/doctor/metrics`, `/doctor/templates`, `/doctor/policies*`, `/doctor/evaluation` → 404 `feature_disabled`; i 5 tool Copilot policy rispondono «Funzione disattivata» (nessuna card bozza) |
| backend | `DOCTOR_SIMULATOR_ENABLED` (`doctor_simulator_enabled`) | `true` | se `false`: `/doctor/scenarios/*` → 404 `feature_disabled`; i 2 tool scenario rispondono «Funzione disattivata» |
| frontend | `DOCTOR_POLICY_UI_ENABLED` (`src/features.ts`) | `true` | kill switch UI di «I miei parametri» |
| frontend | `DOCTOR_LAB_UI_ENABLED` (`src/features.ts`) | `true` | kill switch UI del «Laboratorio» |

Una sezione è visibile solo se **entrambi** sono attivi: flag frontend **e**
`GET /api/doctor/features` (`policy_enabled` / `simulator_enabled`, cache 5 minuti). Finché
la risposta non arriva le sezioni non sono mostrate. Con il flag policy spento spariscono
la tab, la card in Diagnosi e il deep link ricade su Diagnosi; «Simula» nel drawer è
disabilitato se il simulatore è spento. I flag backend sono letti a ogni richiesta (nessun
riavvio necessario lato route).
