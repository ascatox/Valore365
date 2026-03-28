---
title: "Educazione finanziaria 1: template editoriali e payload backend"
status: "Done"
priority: "high"
created: 2026-03-28
labels: ["education", "doctor", "backend", "content", "feature"]
---

# Educazione finanziaria 1: template editoriali e payload backend

## Contesto

Il Portfolio Doctor produce alert e metriche utili, ma oggi non esiste un layer educativo strutturato che traduca gli alert in spiegazioni semplici e controllate.

La codebase ha gia' una buona base:

- `src/backend/app/services/portfolio_doctor/_health.py` genera score, alert e suggerimenti
- `src/backend/app/schemas/portfolio_doctor.py` definisce gli schemi del Doctor
- `src/backend/app/api/portfolio_health.py` espone i dati al frontend

Manca un catalogo editoriale stabile che colleghi `alert.type` a contenuti educativi riusabili.

## Obiettivo

Introdurre il primo layer educativo backend con template hardcoded e payload strutturato, in modo che il frontend possa renderizzare spiegazioni semplici per gli alert prioritari senza dipendere dall'AI.

## Scope minimo

### 1. Catalogo template educativi

Creare un modulo dedicato, ad esempio:

- `src/backend/app/services/portfolio_doctor/education_templates.py`

Ogni template deve includere almeno:

- `code`
- `title`
- `what_it_means`
- `why_it_matters`
- `how_to_read_it`
- `concept`
- `copilot_prompts`

### 2. Mapping alert prioritari

Copertura minima per:

- `geographic_concentration`
- `position_concentration`
- `etf_overlap`
- `high_volatility`
- `high_ter`

Se alcuni alert oggi non esistono ancora con questi codici, allineare i nomi reali del backend invece di introdurre alias arbitrari.

### 3. Estensione schema Doctor

Valutare l'aggiunta di un payload opzionale sugli alert, ad esempio:

- `education: PortfolioHealthEducation | None`

oppure una struttura equivalente nella response globale.

Il payload deve essere semplice e serializzabile, senza HTML o testo generato a runtime da LLM.

### 4. Costruzione payload in API

Durante la generazione della response Doctor:

- associare il template al singolo alert
- includere eventuali dettagli numerici gia' disponibili per leggere meglio il caso reale
- non duplicare l'intera diagnostica tecnica nel blocco education

## File coinvolti

- `src/backend/app/services/portfolio_doctor/_health.py`
- `src/backend/app/schemas/portfolio_doctor.py`
- `src/backend/app/api/portfolio_health.py`
- nuovo file `src/backend/app/services/portfolio_doctor/education_templates.py`

## Criteri di accettazione

- [ ] Esiste un catalogo hardcoded dei template educativi
- [ ] Ogni alert prioritario ha un template associato
- [ ] La response del Doctor espone un payload educativo stabile
- [ ] Il payload non dipende da AI
- [ ] I testi sono in italiano semplice e coerenti con il tono prodotto

## Ordine di implementazione consigliato

1. Censire gli `alert.type` realmente emessi dal backend
2. Definire i 5 template editoriali
3. Estendere gli schemi Pydantic
4. Popolare il payload nella response API
5. Verificare la shape finale con una response reale del Doctor
