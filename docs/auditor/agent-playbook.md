# Auditor dei calcoli — Playbook dell'agente settimanale

Mandato della sessione AI settimanale (TASK-82). Contratto comune: `docs/auditor/architecture.md`;
regole già esistenti: `docs/auditor/rules.md`; metodo di partenza: l'audit MCP di novembre 2026
(`docs/audit-mcp-2026-11/methodology.md`, `audit-findings.md`, `decisions.md` e il brief originale
`backlog/docs/AUDIT_MCP_2026-11-02.md`).

Le regole deterministiche intercettano solo i difetti che qualcuno ha già immaginato. L'audit di
novembre ha trovato i suoi 24 finding facendo domande da utente scettico e incrociando i tool.
Questa sessione rende quel lavoro periodico: **cerca anomalie nuove, le documenta in modo
riproducibile e le propone come task e come bozze di regole. Non corregge mai il codice.**

## 1. Mandato e limiti

L'agente **può**:
- avviare lo stack locale con il seed dell'Auditor (`scripts/auditor/agent_stack.sh`, TASK-82);
- eseguire l'Auditor: `python -m app.services.auditor --user auditor-seed-user --mode agent
  --fail-on P2 --json-out <tmp>/auditor.json --md-out <tmp>/auditor.md`;
- chiamare qualunque tool esposto dal server MCP sui portafogli di prova con
  `scripts/auditor/mcp_call.py` (stessa `run_tool_sync`, nessun login Clerk, provider offline);
- leggere tutto il codice e la documentazione del repository e il backlog;
- scrivere **solo**: `docs/auditor/reports/<YYYY-MM-DD>.md`, nuovi file in `backlog/tasks/`
  (tramite gli strumenti di Backlog.md quando disponibili) e aprire una PR **in bozza** verso `main`
  da un ramo `auditor/agent-<YYYY-MM-DD>`.

L'agente **non può** (divieti assoluti, anche se un'anomalia sembra banale da correggere):
- modificare codice applicativo, test, migrazioni, workflow, script, configurazione, `CLAUDE.md`, o
  `docs/auditor/rules.md` e `architecture.md` (le bozze di regole stanno nel report);
- disattivare, indebolire o rimarcare come difetto noto una regola; cambiare una tolleranza;
- usare dati di produzione, endpoint di produzione, token o segreti; chiamare provider esterni
  (Yahoo, justETF); mettere nel report dati che non vengano dal seed;
- fare merge, push su `main`, deploy, o chiudere/modificare task esistenti (può solo citarli);
- proporre una correzione come fatto: al massimo un'ipotesi di causa con i riferimenti al codice.

Budget per sessione: al massimo 300 chiamate a `mcp_call.py`, 90 minuti di lavoro, 10 sospetti
proposti. Se il budget finisce, il report dice dove si è fermata l'esplorazione.

## 2. Sequenza della sessione

1. **Preparazione.** Ramo `auditor/agent-<data>` da `main` aggiornato. Avvio dello stack locale con il
   seed. Verifica: `mcp_call.py list_portfolios '{}'` restituisce i portafogli 9101…9107.
2. **Auditor.** Esecuzione della CLI con `--fail-on P2`. Ogni `fail` o `error` è annotato nel report
   (sezione «Esito dell'Auditor»), con il rimando alla regola; **non** è un sospetto nuovo.
3. **Esplorazione** secondo la metodologia (§3), un'area alla volta, ruotando l'ordine delle aree
   di settimana in settimana (l'area di partenza = numero della settimana ISO modulo 8).
4. **Verifica** di ogni sospetto: riproduzione, ricalcolo indipendente, deduplica (§5).
5. **Promozione** dei sospetti che soddisfano i criteri (§4): task nel backlog e bozza di regola.
6. **Report** in `docs/auditor/reports/<data>.md` (formato §6) e PR in bozza.

## 3. Metodologia (dall'audit di novembre)

Per ogni tool e ogni portafoglio di prova l'agente si pone queste domande, nell'ordine. Le domande
nascono dai finding di novembre: tra parentesi il finding che le ha motivate.

1. **Unità e scala.** In che unità è il numero (euro, punti percentuali, frazione, indice base 100)?
   È dichiarata? Un TER, un rendimento, un prezzo hanno l'ordine di grandezza atteso? (V-TER-UNIT,
   V365-006, V-XLSX-1000)
2. **Denominatore.** Su cosa è calcolata la percentuale: valore delle posizioni, valore con la
   liquidità, perimetro coperto? È lo stesso in tutti i tool che mostrano un numero con lo stesso
   nome? (V365-007, C6)
3. **Copertura.** Quanta parte del portafoglio ha davvero i dati (prezzi storici, TER, top holdings,
   rendimento da dividendi)? Se è parziale, l'output lo dice? (V365-001, V365-007, C6)
4. **Coerenza fra tool.** Lo stesso numero (valore, liquidità, pesi, classe di uno strumento, TER
   medio, rendimento) è uguale ovunque compaia: riepilogo, posizioni, saldo di cassa, salute,
   Doctor, stress, X-Ray, costi, reddito, performance, vista aggregata? (V365-002, V365-004, TASK-49)
5. **Ricalcolo indipendente.** Il numero si può rifare a mano con gli input che il tool stesso
   espone (export della performance, pesi × shock, quantità × prezzo, somma dei bucket)? Se il
   ricalcolo non torna, quale input manca? (V365-001, C1-TWR-MIXED)
6. **Sensibilità alla composizione.** Due portafogli diversi danno numeri diversi dove devono? Due
   portafogli uguali per classe danno numeri uguali dove devono? (V365-001)
7. **Casi limite.** Portafoglio vuoto, una sola posizione, sola liquidità, nessun target, target che
   sommano meno di 100, prezzo fermo, nessuna chiusura precedente, strumento non classificabile,
   valute diverse, importo di simulazione pari al valore della posizione o oltre. Il tool dà un
   errore chiaro, un `null` con motivo, o un numero inventato (0, valore di default)? (V365-005,
   V-DAYMOVERS-ROOT, V-DIV-MIXED-CCY)
8. **Conservazione.** Le simulazioni conservano il capitale (liquidità prima + aggiunta + vendite −
   acquisti = liquidità dopo, nessuna liquidità negativa, somma dei versamenti = importo)? (V365-003)
9. **Classificazione.** La classe di ogni strumento (azione, obbligazione, oro, materie prime,
   liquidità, cripto, non classificato) è plausibile dal nome e dai dati salvati, ed è la stessa in
   ogni tool? Il veicolo (ETF, ETC, azione) è distinto dalla classe? (V365-002, V365-012,
   V-BOND-QUOTETYPE)
10. **Dati importati.** Prezzi, quantità, valute e date delle transazioni sono plausibili rispetto al
    prezzo di mercato? Ci sono righe identiche? (V365-008, V365-009, V-QUOTE-CCY-L)
11. **Testo contro numeri.** Le note in italiano (`coverage_note`, `tax_note`, `data_quality_note`,
    `methodology_note`) descrivono davvero ciò che i numeri fanno? Una nota promette un perimetro
    diverso da quello calcolato? (V365-007, metodologia §5)
12. **Limiti dichiarati.** Prima di chiamare difetto un comportamento, l'agente verifica se è un
    limite dichiarato nella metodologia o una decisione approvata (`decisions.md`): in quel caso non
    è un sospetto (ma può proporre di renderlo più visibile, come miglioria a bassa priorità).

Aree di esplorazione (rotazione settimanale): 1 stress test; 2 classificazione e X-Ray;
3 ribilanciamento, PAC e what-if; 4 costi e reddito; 5 Monte Carlo e variazioni giornaliere;
6 performance e liquidità; 7 vista aggregata; 8 Doctor 2.0 (metriche, violazioni, Scenario Lab).
Per l'area della settimana l'agente prova almeno le domande 1-8 su tutti i portafogli di prova; per
le altre aree almeno le domande 4 e 7.

Strumenti di ricalcolo ammessi: Python della libreria standard su output salvati in una cartella
temporanea fuori dal repository; `app.services.auditor.offline_returns` per TWR/XIRR; le tabelle di
`app/constants/stress_scenarios.py`. Nessun ricalcolo che importi il codice del servizio da
verificare (si verificherebbe il codice con sé stesso).

## 4. Sospetti e finding

### 4.1 Formato di un sospetto

Ogni sospetto è un blocco nel report, con tutti questi campi:

```markdown
#### S-2026-11-16-01 — <titolo breve in italiano>
- Area: <una delle aree di `AREAS` dell'architettura>
- Tool e argomenti: `get_cost_breakdown` `{"portfolio_id": 9103}`
- Riproduzione: `python scripts/auditor/mcp_call.py get_cost_breakdown '{"portfolio_id": 9103}' --user auditor-seed-user`
- Output (estratto): `{"weighted_ter_pct": 0.212, "covered_market_value_eur": 8500.0, ...}`
- Osservato: <valore e percorso del campo>
- Atteso: <valore o proprietà attesa, con il ricalcolo o il secondo tool che la dimostra>
- Motivo: <perché è un'anomalia: quale domanda del §3, quale incoerenza>
- Riferimenti nel codice: `app/copilot_tools.py:_get_cost_breakdown` (ipotesi, non correzione)
- Deduplica: regole controllate <id>, task controllati <TASK-NN>, report precedenti <data>
- Severità proposta: P0 | P1 | P2 (criteri dell'architettura §4.4)
- Stato: sospetto | confermato | scartato (motivo)
```

### 4.2 Criteri per promuovere un sospetto a finding (confermato)

Tutti e cinque:
1. **Riproducibile**: la stessa chiamata, ripetuta, dà lo stesso output anomalo (seed deterministico).
2. **Dimostrato**: da un ricalcolo indipendente che non torna, da due tool che mostrano valori
   diversi per la stessa grandezza, o da un valore contrario a una tabella approvata o a una
   decisione di `decisions.md`. Un'impressione («sembra alto») non basta.
3. **Non dichiarato**: non è un limite documentato nella metodologia né una decisione approvata o
   ancora aperta (le decisioni aperte non sono difetti: si citano).
4. **Visibile**: cambia un numero o un testo che l'utente, Copilot, il Tribunale o un client MCP
   vedono.
5. **Nuovo**: supera la deduplica (§5).

Un sospetto che non soddisfa 1 o 2 resta nel report come «sospetto» (da riesaminare la settimana
dopo); uno che non soddisfa 3, 4 o 5 è «scartato» con il motivo.

### 4.3 Cosa produce un finding confermato

1. Un task nel backlog (`backlog/tasks/`, con gli strumenti di Backlog.md se disponibili):
   titolo `Auditor: <problema>`, label `auditor` e `backend`, priorità secondo la severità (P0 alta,
   P1 media, P2 bassa), descrizione con l'evidenza riproducibile del §4.1, criteri di accettazione
   che chiedono la correzione **e** l'attivazione della regola proposta. Nessuna assegnazione.
2. Una **bozza di regola** nel report, nel formato delle schede di `rules.md` (id proposto nel gruppo
   giusto, titolo per l'utente, severità, area, finding = id del sospetto, scope, tool e argomenti
   canonici, condizione esatta con i nomi reali dei campi, tolleranze motivate dagli arrotondamenti
   del codice, casi di `skip`, portafoglio di prova che la esercita o modifica del seed necessaria).
   Il catalogo vero lo aggiorna il task di correzione, non l'agente.

## 5. Deduplica

Prima di proporre un sospetto l'agente controlla, nell'ordine, e lo scrive nel campo «Deduplica»:
1. **Regole dell'Auditor**: c'è una regola in `rules.md` la cui condizione copre il caso? Se sì e la
   regola passa, il sospetto è probabilmente un errore di lettura: rileggere; se la regola fallisce,
   è già noto (sezione «Esito dell'Auditor»). Se una regola copre il caso solo in parte, il
   sospetto può proporre di estenderla.
2. **Backlog**: ricerca nei task (strumenti di Backlog.md: ricerca per parole chiave; altrimenti
   `grep -ril` su `backlog/tasks/` e `backlog/completed/`) per nome del tool, nome del campo e
   parole del problema. Un task aperto che lo descrive → citato, non duplicato.
3. **Audit di novembre**: `audit-findings.md` (finding, residui aperti come TASK-41, TASK-45),
   `decisions.md` (decisioni aperte), `regression-results.md` (rischi residui).
4. **Report precedenti** in `docs/auditor/reports/`: un sospetto già proposto e non ancora in un task
   si aggiorna (stessa sigla, nuova data), non si duplica.

## 6. Report della sessione

File `docs/auditor/reports/<YYYY-MM-DD>.md`, in italiano, con queste sezioni:

1. **Sintesi**: data, commit di `main` esaminato, durata, chiamate fatte, area della settimana,
   numero di sospetti (confermati / sospetti / scartati), task creati.
2. **Esito dell'Auditor**: tabella severità × esito della CLI e l'elenco dei `fail`/`error` con il
   rimando alla regola (e al task se è un difetto noto).
3. **Sospetti confermati**: blocchi del §4.1 con stato «confermato», ognuno con il task creato e la
   bozza di regola.
4. **Sospetti da riesaminare** e **scartati** (con motivo).
5. **Copertura dell'esplorazione**: aree e portafogli esaminati, domande del §3 applicate, dove ci si
   è fermati.
6. **Proposte di miglioramento del seed**: casi che i portafogli di prova non contengono.

La PR in bozza contiene solo il report e i task nuovi; descrizione: sintesi, link al report, elenco
dei task. Nessun'altra modifica.

## 7. Attivazione e prova a secco

Sezione che completa TASK-82: comando di avvio della sessione programmata, frequenza, costo
indicativo, come disattivarla e il link alla prova a secco documentata in `docs/auditor/reports/`.
L'attività programmata viene creata dalla sessione che coordina il lavoro solo con la conferma del
proprietario del progetto.
