# UI/UX Refactoring Brief: Valore365 Web App
**Target:** Frontend Developer / UI Engineer
**Obiettivo:** Ottimizzare la data-visualization, ridurre il cognitive load e migliorare l'uso dello spazio nel viewport.

## 1. Ottimizzazione Layout Globale e Navigazione
* **Gestione Notifiche di Sistema (Banner):**
  * **Problema:** Il banner "Aggiornati prezzi..." occupa spazio verticale prezioso (above the fold) in modo statico.
  * **Azione:** Rimuovere il banner statico dal flusso del documento. 
  * **Implementazione:** Sostituirlo con un componente `Badge` o un indicatore di stato testuale (es. un dot verde + "Prezzi aggiornati") posizionato nell'header superiore, in prossimità del bottone `<button>Aggiorna</button>`. Gestire eventuali errori di sync tramite Toast notifications temporanee.
* **Componente di Navigazione Secondaria (Tabs):**
  * **Problema:** I selettori della vista (Panoramica, Posizioni, ecc.) hanno lo styling di un Primary Button (sfondo pieno, border-radius a pillola), creando confusione nella gerarchia delle Call to Action.
  * **Azione:** Eseguire un refactoring visivo da "pill" a "tab" testuale.
  * **Implementazione:** Rimuovere il background-color dal container del tab attivo. Utilizzare un `border-bottom` (es. 2px solid primary-color) e un font-weight `bold` per indicare lo stato `:active` o `aria-selected="true"`.

## 2. Refactoring Tabella `Posizioni` (<PositionsTable />)
Questa vista richiede un upgrade logico per supportare decisioni di investimento più rapide.
* **Raggruppamento Dati (Data Grouping):**
  * **Azione:** Modificare la struttura dati passata alla tabella per supportare il raggruppamento per `assetClass` (Azionario, Obbligazionario, ecc.).
  * **Implementazione:** Introdurre righe espandibili/collassabili (accordion rows) che fungano da header di categoria, mostrando il sub-totale per quell'asset class.
* **Integrazione "Target Allocation":**
  * **Azione:** Inserire una nuova colonna per confrontare l'allocazione attuale con quella desiderata.
  * **Implementazione:** Affiancare alla colonna "Alloc." una colonna "Target". Implementare una logica per calcolare e renderizzare il delta visivo (es. se lo scostamento > 5%, evidenziare la cella o aggiungere un'icona di warning).
* **Color Coding Dinamico per le Barre di Allocazione:**
  * **Azione:** Differenziare visivamente le micro-barre grafiche nella colonna "Alloc.".
  * **Implementazione:** Passare una prop `color` al componente della barra basata su una mappa cromatica definita nel tema (es. `theme.colors.equity`, `theme.colors.bonds`). Evitare il blu monocromatico per tutte le righe.

## 3. Ottimizzazione Data Visualization (Componenti Chart)
* **Assi e Riferimenti (Y-Axis):**
  * **Azione:** Rendere leggibili i grafici ad area senza necessità di interazione (hover).
  * **Implementazione:** Nelle opzioni della libreria di charting (es. Chart.js, Recharts), abilitare la visibilità dei `ticks` per l'asse Y (minimo, massimo e un paio di step intermedi), posizionandoli esternamente o internamente all'area del grafico con opacità ridotta per non disturbare il tracciato.
* **Consolidamento Vista `Performance`:**
  * **Azione:** Ridurre lo scroll verticale unificando i grafici "Guadagno Assoluto" e "Rendimento TWR".
  * **Implementazione:** Creare un singolo chart component con supporto "multi-axis". Utilizzare una legenda interattiva che permetta all'utente di fare il toggle (hide/show) delle due series (Guadagno vs TWR).

## 4. Layout `Mercati` e Gestione Empty States
* **Densità Grid Indici (<MarketsGrid />):**
  * **Azione:** Ottimizzare il CSS Grid per mostrare più dati in meno spazio.
  * **Implementazione:** Ridurre il `padding` interno delle card. Passare a una regola CSS più densa come `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));` per aumentare il numero di colonne sui monitor ultrawide e laptop.
* **Gestione Valori N/D (Null/Undefined):**
  * **Azione:** Fornire contesto agli "Empty States" (es. MWR = N/D).
  * **Implementazione:** Avvolgere i valori di fallback in un componente `<Tooltip />` che, on hover o on focus, esponga un micro-copy esplicativo (es. *"Dati insufficienti o assenza di flussi di cassa per il calcolo del Money-Weighted Return"*).