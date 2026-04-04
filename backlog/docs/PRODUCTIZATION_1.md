# 🚀 Valore365 — Golden Path & Insight Engine (SPEC)

## 🎯 Obiettivo

Costruire una **Golden Path** che permetta all’utente di:

> capire i problemi principali del proprio portafoglio in meno di 2 minuti

Output finale:

* massimo 3 insight
* chiari, semplici, utili
* spiegabili via AI

---

# 🧠 Golden Path (User Flow)

## Step 1 — Login

* login veloce (Google/email)

## Step 2 — Import portafoglio

* CSV (Fineco)
* manuale (minimo)
* demo mode (fondamentale)

## Step 3 — Analisi (loading)

Mostrare:

* “Stiamo analizzando il tuo portafoglio…”
* micro insight in progress

## Step 4 — Risultato

Mostrare **3 insight principali**

Ogni insight:

* titolo
* breve descrizione
* CTA: “Spiegamelo meglio”

## Step 5 — AI Explain

* spiegazione semplice
* no consigli operativi

---

# 🧩 Modello Dati Input

Ogni asset deve essere normalizzato così:

```json
{
  "ticker": "VWCE",
  "name": "Vanguard FTSE All-World",
  "weight": 0.25,
  "asset_class": "Equity",
  "geo_exposure": {
    "USA": 0.62,
    "Europe": 0.18,
    "Emerging Markets": 0.12,
    "Japan": 0.08
  },
  "top_holdings": {
    "Apple": 0.04,
    "Microsoft": 0.035
  }
}
```

---

# 📊 Metriche Aggregate

## 1. Esposizione geografica

Formula:

```
geo[country] += asset.weight * asset.geo_exposure[country]
```

---

## 2. Overlap holdings

```
holdings[name] += asset.weight * asset.top_holdings[name]
```

---

## 3. Asset allocation

```
asset_class[type] += asset.weight
```

---

## 4. Risk score

```
RISK = {
  Equity: 5,
  Bond: 2,
  Gold: 3,
  Cash: 1
}

risk_score = sum(weight * RISK[class])
```

---

## 5. Drawdown stimato

```
DRAWDOWN = {
  Equity: 0.35,
  Bond: 0.10,
  Gold: 0.15,
  Cash: 0
}

drawdown = sum(weight * DRAWDOWN[class])
```

---

# 🚨 Insight Rules

## 🔴 1. Concentrazione geografica

Trigger:

* top area > 60%

Severità:

* > 75% → alta
* 60–75% → media

Output:

* regione dominante
* percentuale

---

## 🟠 2. Overlap

Trigger:

* holding > 8%

Severità:

* > 10% → alta
* 8–10% → media

Output:

* nome holding
* peso
* numero strumenti

---

## 🟡 3. Rischio

Trigger:

* drawdown > 18%
* equity > 75%

Severità:

* > 25% → alta
* 18–25% → media

Output:

* drawdown
* equity %

---

# 📊 Ranking Insight

Formula:

```
score = severity * impact * confidence
```

Ordinare e prendere i primi 3.

---

# 📦 Struttura Insight

```json
{
  "id": "geo_usa",
  "type": "geo_concentration",
  "severity": "high",
  "score": 27,
  "title": "Sei molto concentrato sugli Stati Uniti",
  "short_description": "Il 78% del tuo portafoglio dipende da quest'area.",
  "explanation_data": {
    "region": "USA",
    "weight": 0.78
  },
  "cta_label": "Spiegamelo meglio"
}
```

---

# ⚙️ Algoritmo

```
generate_top_insights(portfolio):
  normalize assets

  geo = aggregate_geo()
  holdings = aggregate_holdings()
  asset_class = aggregate_class()
  risk_score = compute_risk()
  drawdown = compute_drawdown()

  insights = []

  add geo insight
  add overlap insight
  add risk insight

  sort by score
  return top 3
```

---

# 🤖 AI Prompt (System)

```
Sei un educatore finanziario.

Non dare consigli operativi.
Spiega in modo semplice.
Massimo 5 frasi.
Usa esempi concreti.
```

---

# 🤖 AI Prompt (Dynamic)

```
Problema:
{{TITLE}}

Dettagli:
{{DESCRIPTION}}

Spiega in modo semplice:
- perché è un problema
- cosa significa per l’utente

Non dare consigli operativi.
```

---

# 🎨 UX Rules

* massimo 3 insight
* niente grafici complessi iniziali
* una card per insight
* bottone “Spiegamelo meglio”

---

# 🚀 MVP Scope

IN:

* import portfolio
* 3 insight
* AI explain
* demo mode

OUT:

* PAC
* mercati
* analisi avanzate
* app mobile

---

# 📈 Metriche da tracciare

* login
* import completato
* insight visualizzati
* click su explain
* ritorno utente

---

# 🎯 Obiettivo finale

👉 far dire all’utente:

“Non sapevo questa cosa sul mio portafoglio”
