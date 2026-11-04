# Collegare Valore365 a Claude o ChatGPT (guida utente)

Questa guida spiega, passo per passo, come far leggere i tuoi portafogli Valore365 al tuo
assistente AI (Claude o ChatGPT) e come scollegarlo quando vuoi.

> Sei uno sviluppatore o gestisci il server? La documentazione tecnica (configurazione, sicurezza,
> variabili d'ambiente, test) è in [mcp.md](mcp.md).

## Indice

- [Cos'è](#cosè)
- [Cosa può fare l'AI e cosa no](#cosa-può-fare-lai-e-cosa-no)
- [Prima di iniziare](#prima-di-iniziare)
- [L'indirizzo del server](#lindirizzo-del-server)
- [Collegare Claude (web e app)](#collegare-claude-web-e-app)
- [Collegare Claude Desktop](#collegare-claude-desktop)
- [Collegare Claude Code](#collegare-claude-code)
- [Collegare ChatGPT](#collegare-chatgpt)
- [Esempi di domande](#esempi-di-domande)
- [Scollegare e revocare l'accesso](#scollegare-e-revocare-laccesso)
- [Privacy](#privacy)
- [Risoluzione dei problemi](#risoluzione-dei-problemi)

## Cos'è

Valore365 è **AI Ready**: espone un server **MCP** (*Model Context Protocol*, uno standard aperto
per collegare gli assistenti AI a servizi esterni). Una volta collegato, puoi chiedere al tuo
assistente cose come «com'è andato il mio portafoglio quest'anno?» e lui risponde usando i tuoi dati
reali di Valore365, con gli stessi strumenti di analisi del Copilot interno.

Non devi installare nulla su Valore365 né condividere la tua password: autorizzi la connessione
con il tuo normale login Valore365.

## Cosa può fare l'AI e cosa no

**Può (sola lettura):**

- elencare i tuoi portafogli;
- leggere più portafogli **insieme** (da 2 a 20, nella stessa valuta), come la vista aggregata
  dell'app: riepilogo, posizioni, allocazione, performance, transazioni, salute, Monte Carlo,
  stress test e X-Ray complessivi. I portafogli restano separati: è solo una lettura combinata;
- leggere riepilogo, posizioni, liquidità, transazioni recenti, performance, dividendi e costi;
- calcolare analisi come salute del portafoglio, X-Ray (esposizione geografica e settoriale),
  stress test, proiezione Monte Carlo e reddito atteso;
- fare **simulazioni**: ordini di ribilanciamento, effetto di un acquisto o di una vendita,
  ripartizione di un versamento PAC. Sono solo calcoli: non viene registrato nulla.

**Non può:**

- creare, modificare o cancellare portafogli, transazioni, target o impostazioni;
- eseguire ordini o spostare denaro (Valore365 non è collegato al tuo broker);
- vedere i portafogli di altri utenti: ogni richiesta è limitata al tuo account.

Le risposte dell'AI sono generate dal provider che hai scelto (Anthropic o OpenAI) a partire dai
tuoi dati: possono contenere errori e **non sono consulenza finanziaria**.

## Prima di iniziare

Ti servono:

1. un **account Valore365** con almeno un portafoglio (lo stesso con cui accedi all'app);
2. un account **Claude** o **ChatGPT** che permetta di aggiungere connettori personalizzati
   (la disponibilità dipende dal piano e può cambiare nel tempo: verifica nelle impostazioni del
   tuo client);
3. l'**indirizzo del server MCP** (vedi sotto).

## L'indirizzo del server

L'indirizzo del server MCP di Valore365 è:

```
https://valore365.onrender.com/mcp
```

Il modo più semplice per ottenerlo: apri Valore365, vai su **Impostazioni → Copilot** e, nella
sezione **"Collega Claude o ChatGPT (MCP)"**, premi **Copia** accanto all'URL.

> Attenzione: è l'indirizzo del *backend* (le API), non quello della pagina web che apri nel browser.

## Collegare Claude (web e app)

Su [claude.ai](https://claude.ai) (vale anche per le app mobile, che condividono i connettori):

1. Apri **Settings** (Impostazioni) → **Connectors** (Connettori).
2. Premi **Add custom connector** (Aggiungi connettore personalizzato).
3. Inserisci un nome, ad esempio `Valore365`, e l'URL del server MCP. Lascia vuoti i campi OAuth
   avanzati (client id e secret), a meno che chi gestisce il server non ti dica diversamente.
4. Premi **Add**, poi **Connect** (Connetti).
5. Si apre la pagina di login di Valore365: accedi con il tuo account e **autorizza** l'accesso.
6. Torna in chat: dal menu degli strumenti (icona sotto la casella di testo) verifica che
   **Valore365** sia attivo e fai una domanda, ad esempio «Quali portafogli ho su Valore365?».

Nei piani Team ed Enterprise i connettori personalizzati possono essere aggiunti solo da un
amministratore; poi ogni utente fa **Connect** con il proprio login.

## Collegare Claude Desktop

I connettori remoti di Claude Desktop sono gli stessi di claude.ai: se hai già collegato
Valore365 sul web lo trovi anche nell'app. Altrimenti, nell'app, segui gli stessi passi da
**Settings → Connectors → Add custom connector**. Non serve modificare file di configurazione.

## Collegare Claude Code

Nel terminale:

```bash
claude mcp add --transport http valore365 https://valore365.onrender.com/mcp
```

Poi, dentro Claude Code:

1. digita `/mcp`;
2. seleziona `valore365` e scegli di autenticarti;
3. completa il login Valore365 nel browser che si apre e autorizza l'accesso.

Da quel momento puoi chiedere, ad esempio, «Usa valore365 per dirmi le 5 posizioni più pesanti del
mio portafoglio».

## Collegare ChatGPT

Su ChatGPT i connettori personalizzati (chiamati anche *app*) si usano tramite la **modalità
sviluppatore**, disponibile solo su alcuni piani. I nomi dei menu cambiano spesso: se non li trovi,
fa fede la documentazione di OpenAI su "developer mode" e "connectors".

1. Apri **Settings** → **Apps & Connectors** → **Advanced settings** e attiva **Developer mode**.
2. Torna in **Apps & Connectors** e premi **Create** (crea un nuovo connettore).
3. Inserisci nome (`Valore365`), URL del server MCP e, come autenticazione, **OAuth**.
4. Conferma: si apre il login di Valore365, accedi e autorizza l'accesso.
5. In una nuova chat attiva il connettore Valore365 dal menu degli strumenti e fai la tua domanda.

## Esempi di domande

L'assistente sceglie da solo lo strumento giusto; la colonna di destra serve solo a capire cosa
succede dietro le quinte.

| Domanda | Strumento usato |
|---|---|
| «Quali portafogli ho su Valore365?» | `list_portfolios` |
| «Dammi il riepilogo del portafoglio *Principale*: valore, guadagno e variazione di oggi.» | `get_portfolio_summary` |
| «Quali sono le 5 posizioni più pesanti e quanto pesano?» | `get_positions` |
| «Com'è andata la performance da inizio anno e a 1 anno?» | `get_performance` |
| «Quanta liquidità ho e quali sono le ultime transazioni?» | `get_cash_balance`, `get_recent_transactions` |
| «Chi si è mosso di più oggi?» | `get_day_movers` |
| «Il portafoglio è in linea con il target? Quali ordini servirebbero per ribilanciare con 2.000 € di liquidità?» | `get_target_drift`, `calculate_rebalance_orders` |
| «Cosa succederebbe ai pesi se comprassi 1.000 € di VWCE.DE?» | `calculate_what_if` |
| «Come divideresti un PAC da 500 € al mese tra i miei strumenti?» | `calculate_pac_contribution` |
| «Che cos'è lo strumento SWDA.MI che ho in portafoglio?» | `search_asset_info` |
| «Come sta di salute il mio portafoglio?» | `get_portfolio_health` |
| «Fammi l'X-Ray: esposizione geografica, settoriale e primi titoli sottostanti.» | `get_xray_summary` |
| «Quanto pago di TER in totale e quanto mi costerà in 10 anni?» | `get_cost_breakdown` |
| «Quanti dividendi ho incassato e quanto reddito posso aspettarmi?» | `get_dividend_summary`, `get_income_projection` |
| «Simula uno stress test e la proiezione Monte Carlo a 10 anni.» | `get_stress_test`, `get_monte_carlo` |
| «Dammi il riepilogo complessivo di *Parent* e *Wealth*.» | `list_portfolios`, `get_aggregate_summary` |
| «Com'è andata la performance di *Parent* e *Wealth* insieme da inizio anno? E le posizioni complessive?» | `get_aggregate_performance`, `get_aggregate_positions` |

> **Come leggere la performance.** `get_performance` e `get_aggregate_performance` riportano per 1 mese,
> 3 mesi, da inizio anno e 1 anno sia il **TWR** (`twr_1m`...`twr_1y`, rendimento che neutralizza versamenti e
> prelievi) sia l'**MWR** (`mwr_1m`...`mwr_1y`, rendimento money-weighted calcolato con XIRR, ACT/365, che
> tiene conto di quando hai versato). Sono rendimenti **del periodo**, non annualizzati: le versioni annue
> (`twr_annualized_pct`, `mwr_annualized_pct`) compaiono solo per periodi di almeno un anno. Se l'MWR non è
> calcolabile, `mwr_null_reason` dice perché (ad esempio `non_convergente`); `calculation_windows` mostra
> le date effettive usate. Per più portafogli il calcolo è fatto sui valori e flussi sommati, non come media.

> **Come vengono calcolati gli ordini di ribilanciamento.** Si ribilancia solo se almeno uno strumento si
> scosta dal suo peso target di **più di 0,5 punti percentuali**. In quel caso tutti gli strumenti vengono
> riportati al target, anche quelli che si discostano di meno, così le vendite finanziano gli acquisti. La
> liquidità indicata nella domanda si aggiunge a quella già presente nel portafoglio. Commissioni e imposte
> non sono incluse: gli importi sono lordi.

Consiglio: se hai più portafogli, nomina quello che ti interessa («il portafoglio *Pensione*»), oppure
chiedi esplicitamente una vista **complessiva** di quelli che vuoi sommare. Nella vista complessiva
ribilanciamento, drift dal target, simulazioni, dividendi, costi e reddito atteso non sono disponibili:
chiedili per un portafoglio alla volta. I portafogli in valute base diverse non si possono sommare.

## Scollegare e revocare l'accesso

Puoi interrompere il collegamento in qualsiasi momento dal tuo client AI:

- **claude.ai / Claude Desktop**: **Settings → Connectors**, apri **Valore365** e scegli
  **Disconnect** (scollega) oppure rimuovi il connettore.
- **Claude Code**: `claude mcp remove valore365` (oppure da `/mcp` cancella l'autenticazione).
- **ChatGPT**: **Settings → Apps & Connectors**, apri il connettore Valore365 e rimuovilo.

Dopo la disconnessione il client non ha più modo di rinnovare l'accesso. Oggi Valore365 non ha una
pagina interna con l'elenco delle app collegate: se pensi che qualcuno abbia avuto accesso al tuo
account, cambia la password di Valore365 e contatta chi gestisce il servizio.

## Privacy

- Quando fai una domanda, i dati che l'assistente legge da Valore365 (ad esempio valori, posizioni,
  performance, nomi dei portafogli) vengono **inviati al provider AI che hai scelto** (Anthropic per
  Claude, OpenAI per ChatGPT) e trattati secondo le **sue** regole sulla privacy e sulla
  conservazione delle conversazioni. Valuta questo aspetto prima di collegarti.
- La tua password non viene mai condivisa con l'assistente: il client riceve solo un'autorizzazione
  (token) limitata alla lettura, che puoi revocare scollegandolo.
- Valore365 registra, per sicurezza, quale strumento è stato usato e quando, ma non il contenuto
  delle risposte.

## Risoluzione dei problemi

| Problema | Cosa fare |
|---|---|
| **Errore 401 / "Unauthorized" / il client chiede di nuovo il login** | L'autorizzazione è scaduta o non è valida. Riconnetti il connettore (claude.ai: *Connect*; Claude Code: `/mcp` → autenticati di nuovo) e rifai il login Valore365. |
| **Il login non si apre o il collegamento fallisce subito** | Controlla di aver incollato l'URL completo che finisce con `/mcp` e che sia quello del backend (copialo da *Impostazioni → Copilot*). Se ricevi un errore 503 o 404, il servizio MCP non è attivo sul server: contatta chi gestisce Valore365. |
| **"I portafogli aggregati devono avere la stessa valuta base"** | Hai chiesto una vista complessiva di portafogli in valute diverse (es. EUR e USD): chiedila solo per quelli nella stessa valuta. |
| **"Portfolio non trovato"** | L'assistente ha usato l'id di un portafoglio che non esiste o non è tuo. Chiedigli di elencare prima i portafogli («Quali portafogli ho?») e poi di usare quello giusto. Se hai appena cambiato account, scollega e ricollega il connettore. |
| **"Non ho trovato portafogli" / elenco vuoto** | Stai usando un account Valore365 diverso da quello con i tuoi portafogli, oppure non ne hai ancora creato uno. Crea o importa un portafoglio nell'app, oppure riconnetti il connettore con l'account giusto. |
| **Errore 429 / "Too many requests"** | Hai superato il limite di richieste al minuto (di default 60), oppure dalla tua rete sono arrivati troppi tentativi di accesso non validi. Attendi qualche minuto e riprova. |
| **"Troppe richieste in corso" / "Troppe richieste per i tool di calcolo"** | Le analisi più pesanti (Monte Carlo, stress test, X-Ray, proiezioni, simulazioni) hanno un limite più basso (di default 10 ogni minuto) e poche chiamate possono essere in corso insieme. Il messaggio indica dopo quanti secondi riprovare (`retry_after_s`); chiedi un'analisi alla volta. |
| **"Il calcolo ha richiesto troppo tempo"** | L'analisi ha superato il tempo massimo. Riprova più tardi; se succede sempre con lo stesso portafoglio, segnalalo a chi gestisce Valore365. |
| **Errore 403 / "Access denied"** | Il tuo account non è (ancora) abilitato all'uso di MCP: durante il rilascio graduale l'accesso può essere limitato ad alcuni utenti. Contatta chi gestisce Valore365. |
| **L'X-Ray via assistente è meno completo che nell'app** | Via MCP l'X-Ray usa solo i dati ETF già presenti in Valore365 (non ne scarica di nuovi, per restare in sola lettura): per gli ETF senza dati la copertura può essere parziale. |
| **L'assistente non usa Valore365** | Verifica che il connettore sia attivo nella chat e citalo esplicitamente («usa Valore365 per…»). |
| **L'assistente dice di aver modificato qualcosa** | Non è possibile: il server è in sola lettura. Eventuali "ordini" o "acquisti" sono solo simulazioni. |
