# FEATURE: Instant Portfolio Analyzer (No Login) — Codex Ready

## Implementation Status Snapshot

Current repository status as of March 9, 2026:

- public backend route implemented
- parsing, unresolved handling, metrics, scoring, alerts, and suggestions implemented
- frontend page and instant-analyzer components implemented
- score breakdown exposed in API response and rendered in UI
- structured error details returned for fully invalid input
- frontend tests added for success, structured errors, and conditional CTA
- backend unit/integration coverage added for the public analyzer flow

Remaining work is mostly metadata expansion, UI polish, and broader test coverage rather than core feature scaffolding.

## Goal

Build a **public, no-login portfolio analysis experience** that lets a visitor paste positions and instantly receive a **Portfolio Doctor** diagnosis.

This feature is designed to maximize:
- top-of-funnel traffic
- trial conversion
- shareability
- perceived value before signup

Core promise:

> Analyze your portfolio in 30 seconds, without creating an account.

---

## Why this matters

Current friction in most finance tools is:

1. visit site
2. register
3. verify email
4. import data
5. finally see value

This feature changes the flow to:

1. visit site
2. paste holdings
3. get score + insights immediately
4. optionally sign up to save and track

This is **value-first onboarding**.

---

## Scope for v1

The first version should support:

- manual input of positions
- ticker or ISIN input
- value-based analysis
- portfolio score
- top insights / warnings
- optional CTA to create account after results

No persistence required in v1.

---

## User Stories

### Visitor
As a visitor, I want to paste my portfolio positions and receive an instant diagnosis, so I can understand whether my portfolio is well built.

### Visitor
As a visitor, I want to try the tool without signing up, so I can see its value before committing.

### Visitor
As a visitor, I want understandable insights, not just raw numbers, so I know what to improve.

### Product
As the product, I want to convert anonymous visitors into registered users after they see the result.

---

## MVP UX

### Landing page section

Headline:

```text
Check your portfolio health in 30 seconds
```

Subheadline:

```text
Paste your ETF and stock positions and get an instant health score, risk diagnosis, and diversification insights.
```

Primary CTA:

```text
Analyze Portfolio
```

### Input examples

#### Simple text input
```text
VWCE 10000
AGGH 5000
EIMI 2000
```

#### ISIN input
```text
IE00BK5BQT80 10000
IE00BDBRDM35 5000
IE00BKM4GZ66 2000
```

### Result example

```text
Portfolio Score: 74 / 100

Risk: Medium
Diversification: Good
Overlap: Moderate
Costs: Low

Warnings:
- US exposure is high (68%)
- Two ETFs overlap significantly

Suggestions:
- Add more non-US diversification
- Reduce ETF overlap
```

### Conversion CTA after result

```text
Want to save this portfolio and track it over time?
Create a free account
```

---

## Non Goals for v1

Do NOT include in first version:

- broker import
- saved anonymous sessions
- auth-gated persistence
- advanced Monte Carlo
- tax optimization
- rebalancing trades
- PDF export
- social sharing images
- AI chat assistant

These can come later.

---

## Functional Requirements

### Input
The feature must accept:
- ticker + value pairs
- ISIN + value pairs

Optional future support:
- quantity + average price
- CSV upload

### Validation
The system must:
- reject empty input
- reject malformed lines
- require positive numeric values
- ignore extra whitespace
- return line-level parsing errors where possible

### Asset resolution
The system must resolve each line into a known asset using:
- ticker lookup
- ISIN lookup
- existing asset catalog if available

If an asset cannot be resolved:
- mark it as unresolved
- return a helpful error
- do not crash the analysis

### Analysis
The system must compute:
- total portfolio value
- weights by position
- score
- risk level
- diversification quality
- overlap level
- cost efficiency
- alerts
- suggestions

### Output
The API must return:
- parsed positions
- unresolved lines
- metric breakdown
- human-readable insights
- optional signup CTA metadata

---

## Suggested Architecture

### Frontend
Add a dedicated public page:

```text
/frontend/src/pages/InstantPortfolioAnalyzerPage.tsx
```

Recommended components:

```text
/frontend/src/components/instant-analyzer/
  InstantAnalyzerForm.tsx
  InstantAnalyzerResults.tsx
  InstantAnalyzerScoreCard.tsx
  InstantAnalyzerInsights.tsx
  InstantAnalyzerExamples.tsx
```

### Backend
Add a dedicated service and API route:

```text
/backend/app/services/instant_portfolio_analyzer.py
/backend/app/api/instant_portfolio_analyzer.py
```

If your structure uses routers, adapt accordingly.

### Shared domain logic
Reuse or extract logic from Portfolio Doctor if already present:

```text
/backend/app/services/portfolio_doctor.py
/backend/app/services/asset_lookup.py
/backend/app/services/portfolio_metrics.py
```

Goal:
- avoid duplicating metric logic
- anonymous analysis should call the same scoring engine as authenticated portfolio analysis

---

## API Design

### Endpoint

```http
POST /api/public/portfolio/analyze
```

### Request body

```json
{
  "input_mode": "text",
  "positions": [
    {
      "identifier": "VWCE",
      "value": 10000
    },
    {
      "identifier": "AGGH",
      "value": 5000
    }
  ]
}
```

### Alternative raw-text request

```json
{
  "input_mode": "raw_text",
  "raw_text": "VWCE 10000\nAGGH 5000\nEIMI 2000"
}
```

### Response body

```json
{
  "summary": {
    "total_value": 17000,
    "score": 74,
    "risk_level": "medium",
    "diversification": "good",
    "overlap": "moderate",
    "cost_efficiency": "low_cost"
  },
  "positions": [
    {
      "identifier": "VWCE",
      "resolved_symbol": "VWCE",
      "resolved_name": "Vanguard FTSE All-World UCITS ETF",
      "value": 10000,
      "weight": 58.82,
      "status": "resolved"
    }
  ],
  "unresolved": [],
  "metrics": {
    "geographic_exposure": {
      "us": 68.0,
      "europe": 17.0,
      "emerging_markets": 10.0,
      "other": 5.0
    },
    "max_position_weight": 58.82,
    "overlap_score": 61.0,
    "portfolio_volatility": 14.8,
    "weighted_ter": 0.21
  },
  "alerts": [
    {
      "severity": "warning",
      "code": "HIGH_US_EXPOSURE",
      "message": "Your portfolio is heavily exposed to US markets (68%)."
    }
  ],
  "suggestions": [
    {
      "code": "ADD_DIVERSIFICATION",
      "message": "Consider increasing exposure to non-US markets."
    }
  ],
  "cta": {
    "show_signup": true,
    "message": "Create a free account to save and track this portfolio over time."
  }
}
```

---

## Data Contracts

### Pydantic models

Create request/response models, for example:

```text
/backend/app/schemas/instant_portfolio_analyzer.py
```

Suggested models:
- InstantAnalyzeRequest
- RawTextAnalyzeRequest
- ParsedPositionInput
- ResolvedPosition
- PortfolioAnalyzeSummary
- PortfolioAnalyzeMetrics
- PortfolioAnalyzeAlert
- PortfolioAnalyzeSuggestion
- InstantAnalyzeResponse

---

## Parsing Rules

### Raw text parsing
Each line should support:

```text
IDENTIFIER VALUE
```

Examples:
- `VWCE 10000`
- `AGGH 5000`
- `IE00BK5BQT80 10000`

### Parsing algorithm
1. split by newline
2. trim whitespace
3. skip empty lines
4. split by whitespace
5. expect at least 2 tokens
6. first token = identifier
7. last token = numeric value
8. reject non-positive values

### Error handling
Return structured line errors:

```json
{
  "line": 2,
  "raw": "ABC xyz",
  "error": "Invalid numeric value"
}
```

---

## Scoring Model for v1

Use a rule-based score from 0 to 100.

### Score dimensions

```text
Diversification      25
Risk                 25
Concentration        20
Overlap              15
Cost Efficiency      15
```

### Suggested rules

#### Diversification
- 20–25 = well distributed across multiple regions/assets
- 10–19 = acceptable
- 0–9 = highly concentrated

#### Risk
Based on estimated volatility:
- <10% => 25
- 10–15% => 18
- >15% => 10
- >20% => 5

#### Concentration
Based on max position weight:
- <20% => 20
- 20–35% => 15
- 35–50% => 8
- >50% => 3

#### Overlap
- overlap <20 => 15
- overlap 20–40 => 10
- overlap 40–60 => 6
- overlap >60 => 2

#### Cost efficiency
Based on weighted TER:
- <0.20% => 15
- 0.20–0.40% => 12
- 0.40–0.60% => 8
- >0.60% => 3

### Final classification
- 80–100 => excellent
- 70–79 => good
- 60–69 => average
- <60 => weak

---

## Metrics Engine

### Minimum metrics for v1

#### Total value
```python
total_value = sum(position.value for position in positions)
```

#### Position weights
```python
weight = position.value / total_value
```

#### Max position weight
Highest individual position weight.

#### Geographic exposure
Use asset metadata if available:
- US
- Europe
- Emerging Markets
- Other

If exact holdings are not available, use fallback region classification per asset.

#### Overlap score
For v1, use a simplified overlap model:
- if two funds map to similar category buckets, increase overlap
- if both are global/US large cap funds, overlap score rises
- if both are bonds, overlap also rises but maybe less severe than identical equity funds

A later v2 can use real underlying holdings.

#### Portfolio volatility
Use one of:
1. precomputed asset volatility metadata
2. weighted average volatility
3. simplified category-based risk band

v1 should favor robustness over precision.

#### Weighted TER
Use asset metadata TER if available.

---

## Asset Metadata Requirements

The analyzer will need a lightweight metadata source for each supported asset.

Minimum fields:

```json
{
  "symbol": "VWCE",
  "isin": "IE00BK5BQT80",
  "name": "Vanguard FTSE All-World UCITS ETF",
  "asset_type": "etf",
  "region_profile": {
    "us": 0.62,
    "europe": 0.16,
    "emerging_markets": 0.11,
    "other": 0.11
  },
  "risk_band": "equity_global",
  "estimated_volatility": 15.5,
  "ter": 0.22,
  "overlap_bucket": [
    "global_equity",
    "us_large_cap"
  ]
}
```

### v1 implementation option
If you already have an assets table, extend it.
Otherwise create a small curated metadata file for common ETFs.

Possible location:

```text
/backend/app/data/asset_metadata.json
```

or database-backed table if already available.

---

## Insight Rules

Create a deterministic rules engine that produces readable output.

### Example rules

#### High US exposure
Condition:
```python
if us_exposure > 60
```

Output:
```text
Your portfolio is heavily exposed to US markets (X%).
```

#### Low emerging markets exposure
Condition:
```python
if equity_portfolio and emerging_exposure < 5
```

Output:
```text
Emerging markets exposure is low.
```

#### High single-position concentration
Condition:
```python
if max_position_weight > 40
```

Output:
```text
One position represents a large share of your portfolio.
```

#### ETF overlap
Condition:
```python
if overlap_score > 50
```

Output:
```text
Some of your ETFs overlap significantly.
```

#### High cost
Condition:
```python
if weighted_ter > 0.5
```

Output:
```text
Your portfolio costs are relatively high for an ETF portfolio.
```

---

## Suggested Backend Task Breakdown

### Task 1 — Create schemas
Create request and response schemas for the public analyzer API.

### Task 2 — Create raw text parser
Implement parsing from raw text into normalized position inputs.

### Task 3 — Implement asset resolution
Resolve identifier to asset metadata using:
- ticker
- ISIN
- existing lookup services

### Task 4 — Implement metrics engine
Compute:
- total value
- weights
- exposures
- max concentration
- overlap
- volatility
- weighted TER

### Task 5 — Implement score engine
Convert metrics into category scores and final score.

### Task 6 — Implement insight engine
Generate alerts and suggestions from metrics.

### Task 7 — Expose API route
Add POST `/api/public/portfolio/analyze`.

### Task 8 — Add frontend page
Public landing experience with form + results.

### Task 9 — Add CTA to signup
After successful analysis, show save-and-track CTA.

### Task 10 — Add tests
Cover parsing, scoring, API response, and error cases.

---

## Suggested Frontend Task Breakdown

### Form
Implement:
- multiline textarea
- example buttons
- analyze button
- validation errors
- loading state

### Results
Implement:
- score card
- metrics summary
- alerts list
- suggestions list
- unresolved items section
- signup CTA

### Nice-to-have UI details
- prefilled example portfolio
- copy/paste examples
- reset button
- mobile-friendly layout

---

## Pseudocode — Backend Flow

```python
def analyze_public_portfolio(request):
    normalized_inputs = parse_request(request)
    resolved_positions, unresolved, parse_errors = resolve_positions(normalized_inputs)

    if not resolved_positions:
        return error_response("No valid positions found", parse_errors, unresolved)

    metrics = compute_portfolio_metrics(resolved_positions)
    score = compute_portfolio_score(metrics)
    alerts, suggestions = build_insights(metrics)

    return build_response(
        resolved_positions=resolved_positions,
        unresolved=unresolved,
        metrics=metrics,
        score=score,
        alerts=alerts,
        suggestions=suggestions,
    )
```

---

## Pseudocode — Raw Text Parser

```python
def parse_raw_text(raw_text: str) -> list[ParsedPositionInput]:
    results = []
    errors = []

    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 2:
            errors.append({
                "line": line_number,
                "raw": raw_line,
                "error": "Expected format: IDENTIFIER VALUE"
            })
            continue

        identifier = parts[0].strip()
        value_token = parts[-1].replace(",", "")

        try:
            value = float(value_token)
            if value <= 0:
                raise ValueError()
        except ValueError:
            errors.append({
                "line": line_number,
                "raw": raw_line,
                "error": "Invalid numeric value"
            })
            continue

        results.append({
            "identifier": identifier,
            "value": value
        })

    return results, errors
```

---

## Pseudocode — Score Engine

```python
def compute_score(metrics):
    diversification_score = score_diversification(metrics)
    risk_score = score_risk(metrics)
    concentration_score = score_concentration(metrics)
    overlap_score = score_overlap(metrics)
    cost_score = score_cost(metrics)

    total = (
        diversification_score
        + risk_score
        + concentration_score
        + overlap_score
        + cost_score
    )

    return {
        "score": total,
        "band": classify_score(total),
        "breakdown": {
            "diversification": diversification_score,
            "risk": risk_score,
            "concentration": concentration_score,
            "overlap": overlap_score,
            "cost_efficiency": cost_score,
        }
    }
```

---

## Suggested File Structure

```text
backend/
  app/
    api/
      instant_portfolio_analyzer.py
    schemas/
      instant_portfolio_analyzer.py
    services/
      instant_portfolio_analyzer.py
      portfolio_doctor.py
      asset_lookup.py
      portfolio_metrics.py
    data/
      asset_metadata.json

frontend/
  src/
    pages/
      InstantPortfolioAnalyzerPage.tsx
    components/
      instant-analyzer/
        InstantAnalyzerForm.tsx
        InstantAnalyzerResults.tsx
        InstantAnalyzerScoreCard.tsx
        InstantAnalyzerInsights.tsx
```

---

## Testing Requirements

### Backend unit tests
Cover:
- parsing valid raw text
- parsing invalid raw text
- asset resolution
- score calculation
- alerts generation

### API tests
Cover:
- valid analysis request
- invalid request format
- unresolved asset handling
- empty input
- mixed valid/invalid positions

### Frontend tests
Cover:
- form submission
- loading state
- result rendering
- error rendering
- signup CTA visibility

---

## Acceptance Criteria

The feature is complete when:

1. A public user can open the analyzer page without logging in
2. A user can paste at least 3 positions and analyze successfully
3. The backend returns a valid score and insights
4. Unresolved lines are reported cleanly
5. The UI shows score, metrics, alerts, and suggestions
6. The user is invited to sign up after seeing the result
7. The feature works on mobile and desktop
8. Core tests pass

---

## Recommended Rollout Order

### Phase 1
- raw text input
- simple parser
- ticker/ISIN resolution
- score + alerts
- public page

### Phase 2
- better asset metadata coverage
- improved overlap logic
- richer explanations
- examples and polish

### Phase 3
- signup conversion improvements
- save result to account
- compare with benchmarks
- export/share result

---

## Open Questions for Implementation

Codex should inspect the repository and answer these during implementation:

1. Is there already a reusable asset lookup service?
2. Is there already an assets metadata table or file?
3. Is there already a portfolio scoring or analytics service to reuse?
4. Where are public routes currently registered?
5. What is the existing frontend routing pattern?
6. How is API calling currently abstracted in the frontend?
7. Is there already a reusable score card component?

If reusable pieces exist, prefer integration over duplication.

---

## Instructions for Codex

When implementing this feature:

1. Reuse existing portfolio analytics logic wherever possible
2. Avoid duplicating Portfolio Doctor rules if already implemented
3. Keep v1 deterministic and rule-based
4. Prefer robust fallbacks over overly precise but fragile calculations
5. Make the public analyzer independent from authentication
6. Return structured errors, never generic failures
7. Keep UI simple and conversion-focused
8. Add clear TODO comments where metadata coverage needs expansion

---

## Deliverables Expected from Codex

1. Backend API route for public analysis
2. Request/response schemas
3. Parsing service
4. Metrics/scoring service integration
5. Frontend public page
6. Form + results UI
7. Basic tests
8. Minimal documentation update

---

## Final Product Message

This feature should make Valore365 feel like:

> Not just a portfolio tracker, but a tool that tells you whether your portfolio is actually healthy.
