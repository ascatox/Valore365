# Valore365 - Piano Operativo Educazione Finanziaria

## Obiettivo

Portare Valore365 da piattaforma che analizza il portafoglio a prodotto che aiuta anche a capirlo.

Posizionamento desiderato:

```text
Portfolio intelligence + educazione finanziaria contestuale
```

L'obiettivo non e' sostituire il Doctor o il Copilot, ma aggiungere un livello intermedio che trasformi insight e alert in apprendimento pratico.

---

## Perche' farlo ora

Nel prodotto esistono gia':

- un layer deterministico di analisi in `src/backend/app/services/portfolio_doctor/`
- un layer AI in `src/backend/app/copilot/` e `src/backend/app/copilot_tools.py`
- componenti Doctor e Copilot in `src/frontend/valore-frontend/src/components/doctor/` e `src/frontend/valore-frontend/src/components/copilot/`

Manca pero' un layer educativo stabile che:

- traduca gli alert in spiegazioni semplici
- colleghi ogni concetto ai dati reali del portafoglio
- accompagni l'utente da "vedo un problema" a "ho capito cosa significa"

---

## Outcome atteso entro 30 giorni

- L'utente riceve almeno 3 insight comprensibili senza dover aprire il Copilot.
- Ogni alert principale del Doctor ha una spiegazione educativa strutturata.
- Il Copilot viene usato come livello di approfondimento, non come fonte primaria di analisi.
- Esistono segnali misurabili di apprendimento: click, aperture dettagli, quick prompt, ritorno sull'app.

---

## Principi di prodotto

1. Analisi deterministica, spiegazione contestuale.
2. AI solo per spiegare, sintetizzare e guidare, non per diagnosticare.
3. Ogni contenuto educativo deve partire da un dato del portafoglio reale.
4. Linguaggio semplice, italiano chiaro, niente gergo non necessario.
5. Risposte brevi: un concetto, un rischio, un possibile passo successivo.
6. Nessuna consulenza personalizzata o prescrittiva.

---

## Problema da risolvere

Oggi il Doctor produce alert e metriche utili, ma per un utente non esperto rimangono spesso "etichette tecniche":

- esposizione geografica
- concentrazione
- overlap ETF
- volatilita'
- TER

Se l'utente non capisce subito il significato, il rischio e' questo:

```text
vede il problema -> non lo interpreta -> non agisce -> non torna
```

Il layer educativo deve spezzare questo attrito.

---

## Esperienza target

Flusso ideale:

```text
Portfolio -> Doctor -> Alert -> Spiegazione semplice -> Concetto chiave -> Azione rapida -> Copilot
```

Esempio:

```text
Alert: Esposizione USA elevata

Cosa significa?
Gran parte del tuo portafoglio dipende dal mercato USA.

Perche' conta?
Se il mercato USA soffre, una parte ampia del portafoglio puo' scendere insieme.

Concetto chiave
Diversificazione geografica

Passo successivo
Apri "Spiegamelo semplice" oppure chiedi al Copilot come ridurre la concentrazione.
```

---

## Architettura logica

```text
Doctor -> alert strutturato -> template educativo -> UI contestuale -> quick prompt -> Copilot
```

Divisione delle responsabilita':

- Doctor: calcola score, metriche, alert, dettagli
- Education layer: traduce l'alert in spiegazione didattica controllata
- Copilot: approfondisce usando contesto gia' selezionato e prompt rigido

---

## Gap attuali

### Backend

- Esiste uno schema solido per `PortfolioHealthAlert`, ma non un catalogo di contenuti educativi associato agli alert.
- Lo snapshot Copilot e' ricco, ma non contiene un payload esplicitamente pensato per la spiegazione didattica di un singolo alert.

### Frontend

- Esiste `DoctorAlertDetailsModal.tsx`, ma oggi mostra solo approfondimenti tecnici strutturati.
- Esiste `CopilotChat.tsx`, ma il flusso educativo non e' ancora guidato da prompt rapidi strettamente legati all'alert.
- Non esistono ancora glossario e riepilogo "cosa hai imparato oggi".

---

## Scope funzionale

### 1. Template educativi controllati

Creare un catalogo hardcoded che mappi i principali `alert.type` a un contenuto educativo.

Alert prioritari:

- `geographic_concentration`
- `position_concentration`
- `etf_overlap`
- `high_volatility`
- `high_ter`

Struttura proposta:

```json
{
  "code": "geographic_concentration",
  "title": "Esposizione geografica concentrata",
  "what_it_means": "Una parte troppo ampia del portafoglio dipende dalla stessa area geografica.",
  "why_it_matters": "Quando un'area pesa troppo, il portafoglio reagisce in modo meno bilanciato agli shock di mercato.",
  "how_to_read_it": "Guarda la percentuale dell'area dominante e confrontala con il resto del portafoglio.",
  "concept": "Diversificazione geografica",
  "copilot_prompts": [
    "Spiegamelo semplice",
    "Perche' questo alert conta?",
    "Come potrei ridurre questa concentrazione?"
  ]
}
```

Vincolo:

- contenuti editoriali controllati
- nessuna generazione AI del contenuto base

### 2. Blocco educativo nella UI Doctor

Per ogni alert principale mostrare sempre:

- Cosa significa
- Perche' conta
- Come leggerlo nel tuo portafoglio
- Concetto chiave

Questo blocco deve apparire nel dettaglio alert e, quando possibile, direttamente nella card o nel drawer.

### 3. Quick prompts guidati verso il Copilot

Niente chat libera come punto di ingresso principale. Le CTA iniziali devono essere contestuali:

- `Spiegamelo semplice`
- `Qual e' il rischio vero?`
- `Cosa potrei sistemare prima?`

Ogni quick prompt deve passare:

- `page_context=doctor`
- `alert_type`
- metriche essenziali dell'alert
- eventuale concetto educativo associato

### 4. Glossario contestuale

Prima versione con 5 termini:

- diversificazione
- concentrazione
- volatilita'
- overlap
- TER

Ogni termine deve avere:

- definizione semplice
- mini esempio legato al portafoglio
- tono non scolastico

### 5. Riepilogo apprendimento

Dopo la lettura del Doctor o dopo un'interazione col Copilot, mostrare:

```text
Oggi hai imparato:
- il tuo portafoglio e' molto esposto agli USA
- due ETF si sovrappongono
- il costo medio e' sotto controllo
```

Obiettivo: dare una sensazione di progresso cognitivo, non solo diagnostico.

---

## Piano operativo a 4 settimane

## Settimana 1 - Fondamenta contenutistiche

Deliverable:

- catalogo alert prioritari
- mapping `alert.type -> template educativo`
- copy base in italiano semplice
- definizione payload dati minimo per ogni spiegazione

Output atteso:

- una struttura tipo `education_templates.py` o JSON equivalente
- regole editoriali condivise
- prima libreria di 5 template

Criteri di accettazione:

- ogni alert prioritario ha titolo, spiegazione, motivo, concetto, CTA
- nessun testo dipende da AI

## Settimana 2 - Integrazione Doctor UI

Deliverable:

- blocco educativo dentro il dettaglio alert
- CTA rapida per aprire il Copilot con prompt contestuale
- copy coerente tra Doctor e modal

Punti di integrazione probabili:

- `src/frontend/valore-frontend/src/components/doctor/DoctorAlertDetailsModal.tsx`
- nuovo componente `EducationBlock.tsx`
- eventuale arricchimento della response backend se serve un payload gia' pronto

Criteri di accettazione:

- un utente capisce il senso dell'alert senza dover scrivere nulla
- da ogni alert principale puo' aprire un approfondimento guidato

## Settimana 3 - Copilot educativo controllato

Deliverable:

- prompt rapidi contestuali
- contesto ridotto e mirato per spiegare un singolo alert
- vincoli di risposta chiari

Formato risposta consigliato:

```text
1. qual e' il problema
2. perche' conta
3. cosa osservare o migliorare
```

Vincoli:

- max 120-160 parole
- niente invenzioni
- niente consigli prescrittivi forti

Punti di integrazione probabili:

- `src/backend/app/copilot/snapshot.py`
- `src/backend/app/prompts/copilot_system_agentic.txt`
- `src/frontend/valore-frontend/src/components/copilot/CopilotChat.tsx`

## Settimana 4 - Learning loop e misurazione

Deliverable:

- glossario cliccabile
- widget "cosa hai imparato oggi"
- tracciamento eventi
- mini test utenti

Metriche minime da osservare:

- alert detail open rate
- education CTA click-through rate
- quick prompt usage rate
- glossary open rate
- ritorno sul Doctor entro 7 giorni

---

## Scope tecnico

### Backend

File da coinvolgere o estendere:

- `src/backend/app/services/portfolio_doctor/_health.py`
- `src/backend/app/schemas/portfolio_doctor.py`
- `src/backend/app/copilot/snapshot.py`
- `src/backend/app/prompts/copilot_system_agentic.txt`
- nuovo modulo dedicato ai template educativi

Responsabilita' backend:

- definire il catalogo template
- mappare gli alert a contenuti educativi
- fornire al frontend un payload stabile e semplice da renderizzare
- passare al Copilot solo i dati minimi necessari

### Frontend

File da coinvolgere o estendere:

- `src/frontend/valore-frontend/src/components/doctor/DoctorAlertDetailsModal.tsx`
- `src/frontend/valore-frontend/src/components/copilot/CopilotChat.tsx`
- nuovi componenti per `EducationBlock` e `GlossaryTooltip`

Responsabilita' frontend:

- rendere il contenuto educativo in modo leggibile e compatto
- offrire CTA guidate
- non trasformare il flusso in una chat generica

---

## KPI di prodotto

### Attivazione

- percentuale utenti che aprono almeno un dettaglio alert

### Comprensione

- percentuale utenti che cliccano un blocco educativo o un termine glossario
- percentuale utenti che lanciano un quick prompt educativo

### Coinvolgimento

- numero medio di alert approfonditi per sessione
- numero medio di prompt educativi per sessione

### Ritorno

- utenti che tornano nella sezione Doctor entro 7 giorni

---

## Cose da non fare

- lasciare al modello il compito di inventare spiegazioni base
- usare chat libera come UX primaria
- mostrare muri di testo
- confondere spiegazione con consulenza
- introdurre concetti scollegati dal portafoglio reale

---

## MVP consigliato in 2 settimane

Se serve comprimere l'ambito, l'MVP corretto e':

- 5 template educativi hardcoded
- integrazione nel dettaglio alert
- 3 quick prompt guidati
- tracciamento base delle interazioni

Questo basta per validare se il layer educativo aumenta comprensione e ritorno.

---

## Prima sequenza implementativa consigliata

1. Catalogare gli alert reali gia' emessi dal Doctor.
2. Definire il mapping editoriale `alert.type -> template educativo`.
3. Integrare il blocco educativo nel modal Doctor.
4. Aggiungere quick prompt contestuali verso il Copilot.
5. Misurare utilizzo e comprensione prima di estendere il glossario.
