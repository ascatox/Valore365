
 
# <img src="src/frontend/valore-frontend/src/assets/logo-mark.svg" alt="Logo Valore365" width="40"> Valore365

![Python](https://img.shields.io/badge/backend-FastAPI-blue)
![React](https://img.shields.io/badge/frontend-React-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 🧠 Capisci se il tuo portafoglio è davvero ben costruito

Valore365 è una piattaforma di **portfolio intelligence** pensata per investitori italiani che vogliono **analizzare, comprendere e migliorare il proprio portafoglio**.

A differenza dei normali portfolio tracker, Valore365 si concentra sulla **struttura del portafoglio**:

- 🌍 diversificazione geografica  
- 📊 concentrazione degli asset  
- 🔁 sovrapposizione tra ETF  
- ⚠️ rischio complessivo  

---

# ⚡ Demo

Puoi provare l'analisi del portafoglio **senza registrazione**.
https://valore365.vercel.app

### 🧾 Input esempio


VWCE 10000
AGGH 5000
EIMI 2000


### 📊 Output


Portfolio Score: 74

⚠️ Esposizione USA elevata
⚠️ Sovrapposizione ETF
💡 Migliora la diversificazione


---

# 🩺 Portfolio Doctor

Il **Portfolio Doctor** analizza automaticamente il portafoglio e produce una diagnosi.

### 📋 Esempio


Portfolio Score: 74 / 100

📉 Rischio: medio
🌍 Diversificazione: buona
💰 Costi: bassi

⚠️ Avvisi

Esposizione USA elevata

Sovrapposizione ETF


L'analisi è **deterministica e basata su regole**, per garantire risultati coerenti.

---

# 🤖 Portfolio Copilot

Il **Portfolio Copilot** è un assistente AI che aiuta a interpretare la diagnosi del portafoglio.

Puoi chiedere:


Perché il mio score è 72?
Qual è il problema principale del mio portafoglio?
Come posso ridurre il rischio?
Come posso migliorare la diversificazione?


Il Copilot utilizza i dati del **Portfolio Doctor** per fornire spiegazioni chiare.

---

# 📊 Portfolio Tracking

Valore365 permette anche di monitorare il portafoglio nel tempo:

- 📈 performance
- 🧭 allocazione
- 📅 storico del valore
- 🎯 target allocation

---

# 🧩 Vista aggregata

La **vista aggregata** mostra più portafogli come se fossero uno solo (es. broker + conto di risparmio + fondo pensione), **senza creare un nuovo portafoglio** e senza toccare i dati.

- **Come si seleziona**: dal selettore portafoglio (Dashboard, Portfolio, Doctor, FIRE) spunta i portafogli nella sezione "Vista aggregata". La scelta è condivisa tra le pagine e ricordata nel browser; "Torna a un solo portafoglio" ripristina la vista singola. Il badge **Aggregato (N)** indica quanti portafogli sono inclusi (al passaggio del mouse spiega la sola lettura).
- **Stessa valuta base**: si possono aggregare solo portafogli con la stessa valuta base; gli altri compaiono disattivati con il motivo. Servono almeno 2 portafogli, al massimo **20**.
- **Cosa si vede**: valore, P/L, posizioni fuse per strumento (costo medio ponderato, pesi ricalcolati sul totale), andamento, performance TWR/MWR sui flussi combinati, Doctor (salute, X-Ray, Monte Carlo, stress test), FIRE e decumulo, transazioni con la colonna "Portafoglio", Copilot ed export Markdown per AI ("Vista aggregata: A, B, C").
- **Sola lettura**: nuove transazioni, import CSV, modifica/eliminazione di movimenti e le azioni sul portafoglio sono disattivate; per modificare seleziona un solo portafoglio.
- **Non disponibile in aggregato** (dati definiti per singolo portafoglio): target allocation e scostamento dai target, target performance, dettaglio intraday per strumento, liquidità e movimenti di cassa, piani di accumulo (PAC).
- **Errori gestiti**: se un portafoglio della selezione viene eliminato (anche in un'altra scheda) o cambia valuta, la selezione si aggiorna da sola con un avviso.

**API**: ogni risorsa in lettura ha la variante aggregata

```
GET /api/portfolios/aggregate/<risorsa>?portfolio_ids=1&portfolio_ids=2
```

con gli stessi parametri e la stessa risposta della rotta `/api/portfolios/{id}/<risorsa>` (`portfolio_id = 0` e `portfolio_ids` con gli id selezionati). Risorse: `summary`, `positions`, `allocation`, `performers`, `timeseries`, `intraday-timeseries`, `transactions`, `data-coverage`, `performance/*`, `health`, `monte-carlo`, `stress-test`, `xray`, `decumulation`, `export/markdown`. Errori: selezione vuota, più di 20 id o valute diverse → `400 invalid_request`; portafoglio non trovato o di un altro utente → `404 not_found`.

---

# 🔁 ETF Overlap Detection

Molti portafogli contengono ETF che replicano **gli stessi titoli** senza che l’investitore se ne accorga.

Valore365 identifica automaticamente queste **sovrapposizioni**.

---

# ⚙️ Come funziona

Valore365 separa due livelli:


🩺 Portfolio Doctor
↓
analizza il portafoglio

🤖 Portfolio Copilot
↓
spiega i risultati


Questo approccio mantiene l’analisi **affidabile e verificabile**.

---

# 🖼 Screenshot

![Dashboard](docs/images/dashboard.png)
![Dashboard](docs/images/doctor.png)
![Copilot](docs/images/copilot.png)

---

# 🏗 Architettura

### 💻 Frontend

- React
- Vite
- TypeScript

### 🧠 Backend

- FastAPI
- Python

### 🗄 Database

- PostgreSQL

### ☁️ Infrastructure

- Docker
- cloud deployment ready

---

# 📂 Struttura del progetto


database/
src/backend/
src/frontend/
scripts/


---

# ▶️ Avvio in locale

Clonare il repository


git clone https://github.com/ascatox/Valore365

cd Valore365


Avviare i servizi


docker compose --profile dev up --build


Aprire nel browser


http://localhost:8080


---

# 🎯 Visione

Molti strumenti si limitano a **monitorare gli investimenti**.

Valore365 vuole aiutare gli investitori a **capire davvero il portafoglio**.

Domande a cui risponde:

- ❓ Il mio portafoglio è diversificato?
- ❓ Ho troppa esposizione a un mercato?
- ❓ I miei ETF si sovrappongono?
- ❓ Cosa dovrei migliorare?

---

# 🛣 Roadmap

Possibili sviluppi futuri:

- 🔮 simulazioni di portafoglio  
- 📊 analisi ETF più avanzata  
- 🤖 Copilot più evoluto  
- 🏦 supporto a nuovi broker  

---

# 🤝 Contribuire

Contributi e suggerimenti sono benvenuti.

Apri una **issue** o una **pull request**.

---

# 📜 Licenza

MIT License

---

⭐ Se il progetto ti interessa lascia una **stella al repository**
