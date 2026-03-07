# Portfolio Doctor
## Codex-Ready Implementation Spec for Valore365

## Goal

Implement a new feature called **Portfolio Doctor** that analyzes a user portfolio and returns a **portfolio health report**.

This feature must help users understand if their portfolio is well constructed in terms of:

- diversification
- concentration
- ETF overlap
- risk
- costs

The output must be suitable both for:

1. **backend API consumption**
2. **frontend visualization**
3. optional future **LLM explanation layer**

The feature should feel like:

> Import your portfolio and instantly discover whether it is healthy.

---

# Product Requirements

## Main user story

As a user, after importing my portfolio, I want to see a simple health analysis that tells me:

- how strong or weak my portfolio is
- where it is concentrated
- whether I have redundant ETFs
- whether my risk is too high
- what I could improve

## UX expectation

The user lands on a page like:

```text
Portfolio Health

Score: 74 / 100
Risk: Medium
Diversification: Good
Overlap: Moderate
Costs: Low
```

With insights like:

```text
⚠ Your portfolio is heavily exposed to US markets (67%)
⚠ Two ETFs overlap significantly
💡 Consider increasing emerging markets exposure
```

---

# Technical Scope

Implement the feature in **incremental phases**.

## Phase 1

Implement deterministic rule-based analysis only.

No LLM required.

## Phase 2

Add optional natural-language explanation layer based on the structured result.

---

# Expected Backend Structure

Create these files if they do not already exist.

```text
src/backend/app/services/portfolio_doctor.py
src/backend/app/schemas/portfolio_doctor.py
src/backend/app/api/portfolio_health.py
```

If there is already an existing routing structure, integrate accordingly instead of duplicating patterns.

---

# API Contract

## Endpoint

```http
GET /portfolio/{portfolio_id}/health
```

## Response example

```json
{
  "portfolio_id": 123,
  "score": 74,
  "summary": {
    "risk_level": "medium",
    "diversification": "good",
    "overlap": "moderate",
    "cost_efficiency": "low_cost"
  },
  "metrics": {
    "geographic_exposure": {
      "usa": 67.2,
      "europe": 14.5,
      "emerging": 6.3,
      "other": 12.0
    },
    "max_position_weight": 45.1,
    "overlap_score": 58.0,
    "portfolio_volatility": 16.2,
    "weighted_ter": 0.24
  },
  "category_scores": {
    "diversification": 19,
    "risk": 16,
    "concentration": 14,
    "overlap": 11,
    "cost_efficiency": 14
  },
  "alerts": [
    {
      "severity": "warning",
      "type": "geographic_concentration",
      "message": "Your portfolio is heavily exposed to US markets (67.2%)."
    },
    {
      "severity": "warning",
      "type": "etf_overlap",
      "message": "Several holdings appear redundant because ETF overlap is high (58.0%)."
    }
  ],
  "suggestions": [
    {
      "priority": "medium",
      "message": "Consider increasing exposure to non-US equities to improve diversification."
    }
  ]
}
```

---

# Domain Model Assumptions

Use existing portfolio and holdings entities from the project.

Assume the portfolio contains positions such as:

- ETF
- stock
- bond
- cash

Use current market values to compute weights.

If some required metadata is missing, the service should degrade gracefully and still produce a partial analysis.

---

# Required Inputs

The analysis service should use, where available:

- portfolio holdings
- current weights by holding
- asset metadata
- asset class
- region/geography metadata
- TER / cost metadata for ETFs
- historical volatility if available
- ETF overlap metadata if available

If some data is unavailable, use fallbacks.

---

# Fallback Rules

## Geographic exposure fallback

If full look-through exposure is not available:

- use asset-level region classification
- for global ETFs, map to `global` or estimate using simplified exposure buckets if already available

## Volatility fallback

If covariance matrix is not available:

- use weighted average volatility
- if even individual volatility is missing, return `null` and lower confidence

## TER fallback

If TER is missing for some assets:

- compute weighted TER on known assets only
- include an informational note if coverage is incomplete

## Overlap fallback

If precise holdings overlap data is unavailable:

- compute heuristic overlap based on category/index tags
- example: `VWCE` + `S&P 500` = moderate/high overlap heuristic

---

# Core Metrics to Implement

Implement these five metrics first.

## 1. Geographic Exposure

Return percentage allocation by major region.

Suggested shape:

```json
{
  "usa": 67.2,
  "europe": 14.5,
  "emerging": 6.3,
  "other": 12.0
}
```

### Initial rule set

- USA > 60% => warning
- Emerging < 5% => suggestion
- Europe < 10% is not automatically bad, avoid overly prescriptive rules

## 2. Max Position Weight

Detect whether one single holding dominates the portfolio.

### Initial rule set

- > 40% => warning
- > 60% => high risk warning

## 3. ETF Overlap Score

Return a normalized score from 0 to 100 representing redundancy.

### Initial rule set

- > 50 => warning
- > 70 => strong warning

## 4. Portfolio Volatility

Estimate portfolio volatility.

### Initial classification

- < 10 => low
- 10 to 15 => medium
- > 15 => high

## 5. Weighted TER

Calculate weighted total expense ratio.

### Initial rule set

- > 0.50 => warning
- <= 0.30 => low cost

---

# Score Model

Compute a final score from **0 to 100**.

## Category weights

```text
Diversification      25
Risk                 25
Concentration        20
Overlap              15
Cost Efficiency      15
```

## Final classification

```text
80-100 = excellent
70-79  = good
60-69  = average
<60    = weak
```

## Scoring guidance

Each category should independently produce an integer score.

Example:

- diversification: 19 / 25
- risk: 16 / 25
- concentration: 14 / 20
- overlap: 11 / 15
- cost efficiency: 14 / 15

Total = 74 / 100

---

# Insight Engine

Implement a rule-based insight generator.

It should emit:

- alerts
- suggestions
- optional informational notes

## Alert schema

```json
{
  "severity": "warning",
  "type": "geographic_concentration",
  "message": "Your portfolio is heavily exposed to US markets (67.2%)."
}
```

## Suggestion schema

```json
{
  "priority": "medium",
  "message": "Consider increasing exposure to non-US equities to improve diversification."
}
```

## Examples of rules

### Geographic concentration

If `usa > 60`:

- add warning alert

### ETF overlap

If `overlap_score > 50`:

- add warning alert

### High volatility

If `portfolio_volatility > 15`:

- add alert about risk

### High position concentration

If `max_position_weight > 40`:

- add alert about concentration

### Low emerging exposure

If `emerging < 5` and equity-heavy portfolio:

- add non-critical suggestion

### High TER

If `weighted_ter > 0.50`:

- add cost efficiency warning

---

# Implementation Plan

## Step 1 - Schema definitions

Create Pydantic schemas for:

- summary
- metrics
- category scores
- alerts
- suggestions
- final response

Suggested file:

```text
src/backend/app/schemas/portfolio_doctor.py
```

Suggested models:

- `PortfolioHealthSummary`
- `PortfolioHealthMetrics`
- `PortfolioHealthAlert`
- `PortfolioHealthSuggestion`
- `PortfolioHealthResponse`

---

## Step 2 - Service layer

Create service class or functions in:

```text
src/backend/app/services/portfolio_doctor.py
```

Suggested public entry point:

```python
async def analyze_portfolio_health(db, portfolio_id: int, user_id: str | None = None) -> PortfolioHealthResponse:
    ...
```

Suggested internal functions:

```python
def compute_portfolio_weights(holdings) -> list[dict]:
    ...

def compute_geographic_exposure(holdings) -> dict:
    ...

def compute_max_position_weight(holdings) -> float:
    ...

def compute_overlap_score(holdings) -> float:
    ...

def compute_portfolio_volatility(holdings) -> float | None:
    ...

def compute_weighted_ter(holdings) -> float | None:
    ...

def compute_category_scores(metrics: dict) -> dict:
    ...

def build_alerts(metrics: dict) -> list[dict]:
    ...

def build_suggestions(metrics: dict) -> list[dict]:
    ...

def compute_total_score(category_scores: dict) -> int:
    ...

def build_summary(metrics: dict, score: int) -> dict:
    ...
```

---

## Step 3 - API route

Create route file:

```text
src/backend/app/api/portfolio_health.py
```

Example:

```python
from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/portfolio/{portfolio_id}/health", response_model=PortfolioHealthResponse)
async def get_portfolio_health(portfolio_id: int, ...):
    ...
```

Integrate it with the existing router registration pattern already used in the project.

---

## Step 4 - Frontend integration

Create a page or tab called:

```text
Portfolio Health
```

Suggested sections:

1. score card
2. summary badges
3. key metrics
4. alerts list
5. suggestions list

Suggested frontend fields to consume directly from the API response:

- `score`
- `summary`
- `metrics`
- `alerts`
- `suggestions`

---

# Pseudocode for Service

```python
async def analyze_portfolio_health(db, portfolio_id: int, user_id: str | None = None):
    holdings = await load_portfolio_holdings(db, portfolio_id, user_id)

    if not holdings:
        return empty_health_response(portfolio_id)

    weights = compute_portfolio_weights(holdings)
    geographic_exposure = compute_geographic_exposure(weights)
    max_position_weight = compute_max_position_weight(weights)
    overlap_score = compute_overlap_score(weights)
    portfolio_volatility = compute_portfolio_volatility(weights)
    weighted_ter = compute_weighted_ter(weights)

    metrics = {
        "geographic_exposure": geographic_exposure,
        "max_position_weight": max_position_weight,
        "overlap_score": overlap_score,
        "portfolio_volatility": portfolio_volatility,
        "weighted_ter": weighted_ter,
    }

    category_scores = compute_category_scores(metrics)
    score = compute_total_score(category_scores)
    alerts = build_alerts(metrics)
    suggestions = build_suggestions(metrics)
    summary = build_summary(metrics, score)

    return PortfolioHealthResponse(
        portfolio_id=portfolio_id,
        score=score,
        summary=summary,
        metrics=metrics,
        category_scores=category_scores,
        alerts=alerts,
        suggestions=suggestions,
    )
```

---

# Scoring Logic Draft

This does not need to be perfect initially. Use simple deterministic rules.

## Diversification score (0-25)

Start at 25.

Subtract:

- 6 if USA exposure > 60
- 4 if max position > 40
- 4 if overlap > 50
- 3 if emerging < 5 and portfolio is mostly equities

Clamp between 0 and 25.

## Risk score (0-25)

Start at 25.

Subtract:

- 10 if volatility > 15
- 5 if volatility between 12 and 15
- 5 if max position > 40

Clamp between 0 and 25.

## Concentration score (0-20)

Start at 20.

Subtract:

- 6 if max position > 40
- 10 if max position > 60
- 4 if top 3 holdings > 75

Clamp between 0 and 20.

## Overlap score (0-15)

Start at 15.

Subtract:

- 4 if overlap > 40
- 8 if overlap > 50
- 12 if overlap > 70

Clamp between 0 and 15.

## Cost efficiency score (0-15)

Start at 15.

Subtract:

- 3 if TER > 0.30
- 7 if TER > 0.50
- 10 if TER > 0.75

Clamp between 0 and 15.

---

# Initial Heuristic Overlap Logic

Precise ETF look-through data may not yet be available.

Implement a first heuristic approach.

## Heuristic sources

Use fields such as:

- asset type
- benchmark/index name
- category tags
- geography tags
- issuer metadata if helpful
- asset name / symbol pattern matching if needed

## Simple heuristic examples

- `VWCE` + `S&P500 ETF` => high overlap
- `MSCI World` + `S&P500 ETF` => moderate/high overlap
- `Nasdaq 100` + `S&P500 ETF` => moderate overlap
- `Global Aggregate Bond` + `S&P500 ETF` => low overlap

Implement this as a separate helper so that it can later be replaced by true holdings-based overlap.

Suggested function:

```python
def estimate_overlap_between_assets(asset_a, asset_b) -> float:
    ...
```

Then aggregate at portfolio level.

Suggested portfolio-level function:

```python
def compute_overlap_score(weights) -> float:
    ...
```

---

# Error Handling

The endpoint must not fail just because some metadata is missing.

## Requirements

- return partial results when possible
- use `null` for unavailable metrics
- include optional notes if data coverage is incomplete
- avoid hard crashes on missing TER, volatility, geography or overlap metadata

---

# Empty Portfolio Behavior

If the portfolio is empty, return:

```json
{
  "portfolio_id": 123,
  "score": 0,
  "summary": {
    "risk_level": "unknown",
    "diversification": "unknown",
    "overlap": "unknown",
    "cost_efficiency": "unknown"
  },
  "metrics": {
    "geographic_exposure": {},
    "max_position_weight": 0,
    "overlap_score": 0,
    "portfolio_volatility": null,
    "weighted_ter": null
  },
  "category_scores": {
    "diversification": 0,
    "risk": 0,
    "concentration": 0,
    "overlap": 0,
    "cost_efficiency": 0
  },
  "alerts": [],
  "suggestions": []
}
```

---

# Frontend Notes

The backend response should already be ready for UI consumption.

Recommended UI blocks:

## 1. Health score card

Large number with label:

```text
74 / 100
```

## 2. Summary chips

- Risk: Medium
- Diversification: Good
- Overlap: Moderate
- Costs: Low

## 3. Key metrics table

- US exposure
- Europe exposure
- Emerging exposure
- Max position weight
- Overlap score
- Portfolio volatility
- Weighted TER

## 4. Alerts panel

Warnings first, sorted by severity.

## 5. Suggestions panel

Actionable ideas, lower severity than alerts.

---

# Optional Phase 2: LLM Layer

Only after the structured backend is done.

Use the structured JSON output as the prompt context.

Example prompt:

```text
You are a portfolio analysis assistant.
Given these portfolio metrics, explain in simple language the strengths and weaknesses of the portfolio.
Do not provide regulated financial advice.
Focus on diversification, concentration, overlap and cost efficiency.
```

This layer must not replace deterministic scoring. It should only explain it.

---

# Acceptance Criteria

Implement the feature so that:

- a user can call `GET /portfolio/{id}/health`
- the API returns a stable structured response
- the score is deterministic
- alerts and suggestions are generated from explicit rules
- the implementation is resilient to partial metadata
- the output is directly consumable by the frontend

---

# Nice-to-Have After MVP

Not required for the first implementation, but keep the design extensible for:

- benchmark comparison
- historical stress scenarios (2008, Covid, etc.)
- Monte Carlo health simulation
- household-level aggregated portfolio doctor
- tax efficiency signals
- AI-generated explanation and onboarding insights

---

# Important Implementation Notes for Codex

1. Reuse existing project patterns wherever possible.
2. Do not introduce a parallel architecture if similar service/schema/router patterns already exist.
3. Prefer simple deterministic logic over complex finance modeling for MVP.
4. Make helper functions small and testable.
5. Keep overlap logic isolated so it can later be replaced with a more precise model.
6. Ensure the endpoint remains fast enough for interactive UI usage.
7. Add unit tests if the repository already has a testing pattern.

---

# Final Deliverable

Implement the full MVP of Portfolio Doctor with:

- backend schema
- backend service
- API route
- deterministic scoring
- alerts and suggestions
- frontend-ready structured response

If frontend implementation is included, create a simple first version of the Portfolio Health page using the response fields above.
