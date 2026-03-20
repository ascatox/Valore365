# Proposte di Ottimizzazione Backend — Valore365

Questo documento raccoglie le analisi sui casi limite (edge cases) e le proposte di ottimizzazione per i calcoli del portafoglio, i rendimenti e le proiezioni FIRE nel backend di Valore365.

---

## 1. Tassazione Mista e Aliquote Agevolate

**Contesto:** Il piano FIRE e le proiezioni dei dividendi utilizzano un'aliquota fiscale fissa al 26% (default per l'Italia).
**Problema:** I portafogli misti contengono spesso titoli di Stato (es. bond governativi dell'Eurozona, BTP, bond legati all'inflazione) che in Italia beneficiano di un'aliquota agevolata al 12,5%. L'applicazione generalizzata del 26% porta a una sottostima del reddito netto reale e della longevità del portafoglio nel modulo di decumulo.
**Soluzione Proposta:** * Implementare il calcolo di un'aliquota fiscale media ponderata a livello di portafoglio, basata sull'asset allocation reale.
* Distinguere il flag fiscale a livello di anagrafica titolo/ETF per applicare il 12,5% o il 26% in modo dinamico.

---

## 2. Motore Monte Carlo: Distribuzione dei Rendimenti

**Contesto:** La proiezione del portafoglio utilizza uno shock gaussiano standard `N(0, 1)` per generare i log-rendimenti futuri.
**Problema:** I mercati finanziari storicamente non seguono una distribuzione normale perfetta, presentando asimmetria e code grasse (*fat tails*). L'uso esclusivo della distribuzione normale rischia di sottostimare la frequenza e la gravità dei drawdown estremi, rendendo le proiezioni P10 o le probabilità di esaurimento capitale troppo ottimistiche.
**Soluzione Proposta:**
* Valutare l'introduzione di un modello basato sul *historical bootstrap* (campionamento casuale dei rendimenti storici effettivi).
* In alternativa, implementare una distribuzione t di Student con gradi di libertà calibrati sullo storico per gestire meglio le code grasse negli stress test.

---

## 3. Convergenza e Soluzioni Multiple per IRR (MWR)

**Contesto:** Il calcolo del Money-Weighted Return cerca il tasso che azzera il Valore Attuale Netto.
**Problema:** Matematicamente, se i flussi di cassa cambiano segno più volte nel tempo (es. sequenze di grandi depositi alternati a prelievi significativi), la formula può avere radici multiple, restituendo tassi di rendimento matematicamente corretti ma privi di senso economico.
**Soluzione Proposta:**
* Impostare e validare limiti di ricerca (bounds) stringenti e realistici (es. tra -99% e +1000%) per il metodo di Brent in `scipy.optimize.brentq`.
* Aggiungere un log di warning nel backend se la curva del NPV interseca lo zero in più punti nel range analizzato.

---

## 4. Tasso di Crescita Dinamico dei Dividendi

**Contesto:** La proiezione del reddito a 1, 3 e 5 anni assume una crescita composta fissa del 3% annuo per tutti gli asset.
**Problema:** Mentre un tasso del 3% è un'euristica solida per l'azionario globale, risulta impreciso per altre asset class. Le obbligazioni governative o i corporate bond a tasso fisso non offrono una crescita strutturale della cedola nel tempo. Applicare il 3% generalizzato sovrastima i rendimenti futuri della componente a reddito fisso.
**Soluzione Proposta:**
* Differenziare le stime di crescita: mantenere il 3% (o un calcolo storico) per la componente azionaria e impostare uno 0% di crescita strutturale per i dividendi/cedole derivanti da strumenti a reddito fisso.