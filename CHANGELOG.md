# Changelog

Tutte le modifiche rilevanti di Valore365 sono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il progetto
adotta il [Semantic Versioning](https://semver.org/lang/it/).

## [Unreleased]

### Added

- **Portfolio Doctor 2.0** — parametri personali verificabili accanto alla diagnosi
  standard (task backlog TASK-56).
  - **I miei parametri** (Doctor Policy): regole personali per scope (singolo
    portafoglio o vista aggregata, indipendenti fra loro) su 8 metriche MVP — quota
    azionaria, obbligazionaria e oro, peso massimo singola posizione, peso prime tre
    posizioni, esposizione USA look-through, TER medio ponderato, overlap ETF.
    Metodologia `doctor-policy-1.0`: `docs/doctor2/financial-methodology.md`.
  - **Policy Evaluation** deterministica `PASS` / `FAIL` / `UNKNOWN` /
    `NOT_APPLICABLE` / `INACTIVE` con flag «vicino al limite», copertura, bounds
    conservativi ed evidenze (denominatore, strumenti che contribuiscono, data delle
    quote); mai `PASS` su dati stale o non verificabili.
  - Editor con flusso validazione → anteprima (diff e conformità prima/dopo sugli stessi
    dati) → conferma → salvataggio; template illustrativi (Bilanciato, Prudente,
    Dinamico); storico versioni con fonte e ripristino come nuova versione.
  - **Copilot assistito**: tool `read_doctor_policy`, `read_doctor_metrics`,
    `read_doctor_violations`, `validate_policy_draft`, `preview_policy`,
    `build_doctor_scenario`, `compare_doctor_scenarios` nella pagina Doctor; le bozze
    arrivano come card «Bozza di parametri» (evento SSE `policy_draft`) e si salvano solo
    con «Conferma e salva».
  - **Laboratorio** (Scenario Lab): fino a 3 scenari (acquisti/vendite, solo nuova
    liquidità, ribilanciamento) confrontati con il portafoglio attuale, con fattibilità,
    liquidità necessaria senza vendite, regole risolte/nuove violazioni; simulazione pura
    senza scritture.
  - API REST `/api/doctor/*` (features, metrics, templates, policies, validate,
    preview, versions, restore, evaluation, scenarios/preview, scenarios/compare):
    `docs/doctor2/api-contracts.md`.
  - Migrazione `database/migrations/20261104_01_doctor_policies.sql` (tabelle
    `doctor_policy_sets`, `doctor_policy_scope_members`, `doctor_policy_versions`,
    `doctor_confirmation_tokens`).
  - Feature flag backend `DOCTOR_POLICY_ENABLED` e `DOCTOR_SIMULATOR_ENABLED` (default
    `true`, endpoint `GET /api/doctor/features`) e kill switch frontend in `src/features.ts`.
  - MCP: sei tool Doctor in sola lettura (`preview_policy` escluso), con `portfolio_ids`
    opzionale per le policy aggregate.
  - Documentazione: `docs/doctor2/architecture.md`, `docs/doctor2/ui-spec.md`,
    `docs/doctor2/open-decisions.md`.
- **Tribunale del portafoglio** — nuova sezione del Doctor (task backlog TASK-60…71): tre
  voci AI con filosofie diverse (*L'indicizzatore*, *Il fattoriale*, *Il prudente*)
  discutono lo stesso portafoglio, singolo o aggregato.
  - **Fascicolo** deterministico di al massimo 40 fatti del Doctor (id stabili `F1`…,
    valore formattato, fonte, qualità, citabilità) con hash; nessun LLM lo produce.
  - **Seduta** in tre fasi (apertura in parallelo, replica, sintesi con punti condivisi,
    punti contesi e domande aperte; mai un vincitore) in streaming SSE
    (`POST /api/doctor/tribunal/sessions`), con `GET /api/doctor/tribunal/status` e
    `GET /api/doctor/tribunal/sessions/latest`; contratto `tribunale-1.0` in
    `docs/tribunale/api-contracts.md`.
  - Chiamata strutturata al modello (`copilot/structured.py`) per OpenAI, Anthropic, Gemini e
    OpenRouter; numeri solo tramite segnaposto `{Fn}` sostituiti dal backend.
  - **Verificatore** deterministico: scarta cifre libere, fatti inesistenti o non
    citabili, strumenti fuori dal portafoglio, indicazioni operative e verdetti prima che
    raggiungano l'utente, che vede solo i conteggi per voce e per codice.
  - Sedute salvate cifrate (ultima per utente e scope), riuso a fascicolo invariato,
    limite giornaliero con la chiave del server; migrazione
    `database/migrations/20261110_01_tribunal_sessions.sql`.
  - Feature flag `DOCTOR_TRIBUNAL_ENABLED` (default `true`, esposto come `tribunal_enabled`
    in `GET /api/doctor/features`) e `DOCTOR_TRIBUNAL_DAILY_LIMIT` (default `3`).
  - Prove avversarie su Postgres reale (`tests/integration/test_tribunal_adversarial.py`),
    E2E Playwright con LLM finto (`scripts/e2e/tribunal_stack.sh`, `tribunal_e2e.cjs`,
    `tribunal_fake_llm.py`) e script di valutazione di prompt e modello
    (`scripts/e2e/tribunal_eval.py`); esiti in `docs/tribunale/test-report.md`.

### Changed

- Pagina Doctor organizzata in tre sezioni — **Diagnosi**, **I miei parametri**,
  **Laboratorio** — con deep link `?section=parametri` / `?section=laboratorio`
  (`docs/doctor2/ui-spec.md`). La card «I miei parametri» in Diagnosi resta separata dal
  punteggio Doctor, che non cambia (Health Score invariato).
- Doctor Copilot responsive: pannello laterale su desktop, drawer su tablet, bottom
  sheet su mobile.
- Copilot: allowlist dei tool applicata anche a runtime (un tool fuori dalla pagina
  richiesto dal modello viene rifiutato); prompt con instradamento verso `/fire`
  (capitale, rendita, pensione) e `/portfolio` (ordini).

### Fixed

- Doctor: ordine degli argomenti nel prompt Copilot aperto dai dettagli di un alert
  (`handleDoctorPrompt(prompt, alert)`), che prima scambiava prompt e alert; aggiunto
  test `Doctor.alertPrompt.test.tsx`.
- Doctor: in Privacy Mode il riepilogo testuale copiato maschera lo score
  («Score: ******/100»), come già facevano la card e l'immagine condivisa.
- Tribunale: il verificatore non si lasciava aggirare da lettere cirilliche o greche identiche
  a quelle latine né da accenti combinanti («cоmprare», «VWСE», «cómprare»): ora li
  riconduce a lettere latine prima dei controlli su strumenti, indicazioni operative e verdetti.
- Copilot (chiamata strutturata): i log e i messaggi d'errore di una risposta fuori schema
  non riportano più il testo prodotto dal modello, solo il percorso e la regola violata.
- PAC (`calculate_pac_contribution`, Copilot e MCP): con nessuno strumento sotto il peso
  obiettivo (tutti a target o sopra, per esempio target che sommano meno di 100) il tool
  dichiarava allocato l'intero importo con una distribuzione vuota. Ora risponde con
  `total_allocated` 0, `unallocated_amount` pari all'importo e una nota che spiega perché; i
  versamenti sono ripartiti al centesimo, quindi la loro somma è sempre esattamente
  `total_allocated`. La regola dell'Auditor `B-PAC-SUM` non è più un difetto noto (TASK-83).

### Security

- Nessun salvataggio di policy senza **token di conferma monouso** lato server (TTL 15
  minuti, legato a utente, scope, hash del documento e versione base; in DB solo lo
  sha256). Il token non viene mai inviato al LLM né scritto nei log, e le bozze del
  Copilot non vengono salvate nella cronologia locale della chat.
- Optimistic locking sulle versioni (409 `version_conflict`): un salvataggio vecchio non
  sovrascrive quello recente.
- Autorizzazione su tutti i portafogli dello scope a ogni lettura/scrittura (404 non
  rivelatore); scope mai deciso dal LLM; RLS attiva senza policy sulle nuove tabelle.
- MCP esterno resta read-only; testi dei tool ripuliti da caratteri di controllo/bidi.
- Il Laboratorio non scrive su transazioni o posizioni (verificato dai test).
- Privacy Mode nelle nuove sezioni: importi in valuta mascherati (`******`), anche dentro
  i testi del backend (motivi, note, avvertenze, spiegazioni); le percentuali restano
  visibili. Le risposte testuali del Copilot non sono ancora mascherate.
- Punti aperti e rischi residui: `docs/doctor2/open-decisions.md`.
