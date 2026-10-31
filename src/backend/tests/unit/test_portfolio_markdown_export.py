from app.services.portfolio_markdown_export import render_snapshot_markdown


def _full_snapshot() -> dict:
    return {
        'portfolio': {
            'name': 'Il mio portafoglio',
            'base_currency': 'EUR',
            'market_value': 10500.0,
            'cost_basis': 10000.0,
            'unrealized_pl': 500.0,
            'unrealized_pl_pct': 5.0,
            'day_change': 50.0,
            'day_change_pct': 0.5,
            'cash_balance': 1000.0,
            'total_positions': 2,
        },
        'positions': [
            {'symbol': 'VWCE', 'name': 'Vanguard FTSE All-World', 'weight': 60.0,
             'market_value': 6300.0, 'unrealized_pl_pct': 7.0, 'day_change_pct': 0.4},
            {'symbol': 'AGGH', 'name': 'iShares Global Aggregate Bond', 'weight': 40.0,
             'market_value': 4200.0, 'unrealized_pl_pct': 2.0, 'day_change_pct': 0.1},
        ],
        'doctor': {
            'score': 82,
            'risk_level': 'medio',
            'diversification': 'buona',
            'overlap': 'bassa',
            'cost_efficiency': 'ottima',
            'max_position_weight': 60.0,
            'overlap_score': 10.0,
            'portfolio_volatility': 12.5,
            'weighted_ter': 0.15,
            'top_alerts': ['Concentrazione elevata su VWCE'],
            'top_suggestions': ['Valuta di ribilanciare verso i bond'],
        },
        'doctor_monte_carlo': {
            'annualized_mean_return_pct': 5.5,
            'annualized_volatility_pct': 12.0,
            'projections': [{'year': 5, 'p25': 11000, 'p50': 13000, 'p75': 15000}],
        },
        'target_drift': [
            {'symbol': 'VWCE', 'current_weight': 60.0, 'target_weight': 55.0, 'drift': 5.0},
        ],
        'best_performer': {'symbol': 'VWCE', 'day_change_pct': 0.4},
        'worst_performer': {'symbol': 'AGGH', 'day_change_pct': 0.1},
        'pac_plans': {
            'active_rules': [
                {'symbol': 'VWCE', 'asset_name': 'Vanguard FTSE All-World', 'mode': 'amount',
                 'amount': 500.0, 'quantity': None, 'frequency': 'monthly',
                 'day_of_month': 1, 'day_of_week': None, 'start_date': '2025-01-01', 'end_date': None},
            ],
            'pending_executions_count': 1,
        },
    }


def test_render_full_snapshot_contains_all_sections():
    performance_rows = [['1 anno', '5.00%', '4.80%', '5.00%', '4.80%', '8 500.00', '9 000.00', '500.00']]

    markdown = render_snapshot_markdown(_full_snapshot(), 1, performance_rows)

    assert markdown.startswith('# Il mio portafoglio')
    for heading in (
        '## Riepilogo',
        '## Posizioni principali',
        '## Performance',
        '## Salute del portafoglio',
        '## Proiezione Monte Carlo',
        '## Scostamento dai target di allocazione',
        '## Migliore e peggiore di giornata',
        '## Piani di accumulo (PAC) attivi',
    ):
        assert heading in markdown
    assert '| VWCE |' in markdown
    assert '| 1 anno | 5.00% | 4.80% |' in markdown
    assert 'Concentrazione elevata su VWCE' in markdown
    assert 'Esecuzioni PAC in attesa: 1' in markdown


def test_render_minimal_snapshot_omits_optional_sections():
    snapshot = {
        'portfolio': {
            'name': 'Vuoto',
            'base_currency': 'EUR',
            'market_value': 0.0,
            'cost_basis': 0.0,
            'unrealized_pl': 0.0,
            'unrealized_pl_pct': 0.0,
            'day_change': 0.0,
            'day_change_pct': 0.0,
            'cash_balance': 0.0,
        },
    }

    markdown = render_snapshot_markdown(snapshot, 7, performance_rows=None)

    assert '## Riepilogo' in markdown
    for heading in (
        '## Posizioni principali',
        '## Performance',
        '## Salute del portafoglio',
        '## Proiezione Monte Carlo',
        '## Scostamento dai target di allocazione',
        '## Piani di accumulo (PAC) attivi',
    ):
        assert heading not in markdown


def test_export_labels_state_units_and_definitions():
    performance_rows = [['1 mese', 'N/D', 'N/D', 'N/D', 'N/D', 'N/D', '-12 000.00', 'N/D']]

    markdown = render_snapshot_markdown(_full_snapshot(), 1, performance_rows)

    assert 'indici base 100' in markdown
    assert 'P25 (indice)' in markdown
    assert 'Valore iniziale' in markdown
    assert 'valore finale (liquidità inclusa) - valore iniziale - netto investito' in markdown
    assert 'N/D = dato non calcolabile' in markdown
    assert 'media ponderata delle volatilità storiche dei singoli strumenti' in markdown
    assert 'la maggiore tra la volatilità realizzata' in markdown
    assert 'Non include dividendi' in markdown


# --- Vista aggregata (TASK-29) -------------------------------------------------

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from app.models import PerformanceSummary, PortfolioSummary, Position, TWRResult, MWRResult  # noqa: E402
from app.repository import aggregate_identity, normalize_portfolio_ids  # noqa: E402
from app.repository._scope import MIXED_CURRENCY_MESSAGE, NOT_FOUND_MESSAGE  # noqa: E402
from app.services import portfolio_markdown_export as export  # noqa: E402

_CURRENCIES = {1: 'EUR', 2: 'EUR', 3: 'USD'}


def _scope(ids):
    ids = normalize_portfolio_ids(ids)
    if any(pid not in _CURRENCIES for pid in ids):
        raise ValueError(NOT_FOUND_MESSAGE)
    if len({_CURRENCIES[pid] for pid in ids}) > 1:
        raise ValueError(MIXED_CURRENCY_MESSAGE)
    return ids


class _AggregateRepo:
    def __init__(self, positions=None):
        self.calls = []
        self._positions = positions if positions is not None else [
            Position(asset_id=10, symbol='VWCE', name='Vanguard FTSE All-World', quantity=10, avg_cost=100,
                     market_price=120, market_value=1200, unrealized_pl=200, unrealized_pl_pct=20, weight=75,
                     day_change_pct=1.5),
            Position(asset_id=11, symbol='AGGH', name='Global Aggregate Bond', quantity=10, avg_cost=40,
                     market_price=40, market_value=400, unrealized_pl=0, unrealized_pl_pct=0, weight=25,
                     day_change_pct=-0.5),
        ]

    def get_summary_multi(self, ids, user_id):
        ids = _scope(ids)
        self.calls.append(('summary', ids))
        return PortfolioSummary(
            **aggregate_identity(ids), base_currency='EUR', market_value=1600, cost_basis=1400,
            unrealized_pl=200, unrealized_pl_pct=14.29, cash_balance=300,
        )

    def get_positions_multi(self, ids, user_id):
        self.calls.append(('positions', _scope(ids)))
        return self._positions

    def list_portfolios(self, user_id):
        return [SimpleNamespace(id=1, name='Broker'), SimpleNamespace(id=2, name='Banca')]

    # Per-portfolio reads must never be used by the aggregate export.
    def list_portfolio_target_allocations(self, *a, **k):
        pytest.fail('target allocation is per portfolio')

    def list_pac_rules(self, *a, **k):
        pytest.fail('PAC rules are per portfolio')


class _AggregatePerformance:
    def __init__(self):
        self.periods = []

    def get_performance_summary(self, ids, user_id, period):
        assert list(ids) == [1, 2]
        self.periods.append(period)
        twr = TWRResult(twr_pct=5.0, twr_annualized_pct=5.0, period_days=365, start_date='2025-10-31', end_date='2026-10-31')
        mwr = MWRResult(mwr_pct=4.0, period_days=365, start_date='2025-10-31', end_date='2026-10-31', converged=True)
        return PerformanceSummary(
            period=period, period_label=f'periodo {period}', start_date='2025-10-31', end_date='2026-10-31',
            period_days=365, twr=twr, mwr=mwr, total_deposits=100, total_withdrawals=0, net_invested=100,
            initial_value=0, current_value=110, absolute_gain=10,
        )


@pytest.fixture
def _doctor(monkeypatch):
    calls = []

    def _health(repo, ids, user_id):
        calls.append(('health', list(ids)))
        return SimpleNamespace(
            score=70,
            summary=SimpleNamespace(risk_level='medio', diversification='buona', overlap='bassa', cost_efficiency='ottima'),
            metrics=SimpleNamespace(max_position_weight=75, max_single_security_weight=None, overlap_score=5,
                                    portfolio_volatility=11, weighted_ter=0.2),
            alerts=[SimpleNamespace(message='Concentrazione su VWCE')],
            suggestions=[],
        )

    def _monte_carlo(repo, ids, user_id):
        calls.append(('monte-carlo', list(ids)))
        return SimpleNamespace(
            annualized_mean_return_pct=5, annualized_volatility_pct=12, horizons=[5],
            projections=[SimpleNamespace(year=5, p25=110, p50=125, p75=140)],
        )

    monkeypatch.setattr(export, 'analyze_portfolio_health', _health)
    monkeypatch.setattr(export, 'run_monte_carlo_projection', _monte_carlo)
    monkeypatch.setattr(export, '_load_holdings', lambda repo, ids, user_id: calls.append(('holdings', list(ids))) or [])
    monkeypatch.setattr(export, 'compute_weighted_ter', lambda holdings, repo: 0.18)
    return calls


def test_aggregate_markdown_lists_the_portfolios_and_uses_merged_data(_doctor):
    repo, perf = _AggregateRepo(), _AggregatePerformance()

    markdown = export.build_aggregate_portfolio_markdown(repo, perf, [2, 1, 2], 'u')

    assert markdown.startswith('# Vista aggregata — Snapshot portafogli')
    assert 'Vista aggregata: Banca, Broker' in markdown
    assert repo.calls == [('summary', [2, 1]), ('positions', [2, 1])]
    assert ('health', [2, 1]) in _doctor and ('monte-carlo', [2, 1]) in _doctor and ('holdings', [2, 1]) in _doctor
    assert '| Valore di mercato | 1 600.00 |' in markdown
    assert '| Liquidità | 300.00 |' in markdown
    assert '| Numero posizioni | 2 |' in markdown
    assert '| TER medio ponderato | 0.180% |' in markdown
    assert '| VWCE |' in markdown and '| AGGH |' in markdown
    assert '## Salute del portafoglio' in markdown and 'Concentrazione su VWCE' in markdown
    assert '## Proiezione Monte Carlo' in markdown
    assert '- Migliore: VWCE (1.50%)' in markdown
    assert '- Peggiore: AGGH (-0.50%)' in markdown


def test_aggregate_markdown_omits_per_portfolio_sections_and_says_so(_doctor):
    markdown = export.build_aggregate_portfolio_markdown(_AggregateRepo(), _AggregatePerformance(), [1, 2], 'u')

    assert '## Scostamento dai target di allocazione' not in markdown
    assert '## Piani di accumulo (PAC) attivi' not in markdown
    assert '## Non inclusi nella vista aggregata' in markdown
    assert 'target di allocazione' in markdown.split('## Non inclusi nella vista aggregata')[1]
    assert 'PAC' in markdown.split('## Non inclusi nella vista aggregata')[1]


def test_aggregate_markdown_performance_runs_on_the_id_list(monkeypatch):
    perf = _AggregatePerformance()
    monkeypatch.setattr(export, 'analyze_portfolio_health', lambda *a: (_ for _ in ()).throw(ValueError('x')))
    monkeypatch.setattr(export, 'run_monte_carlo_projection', lambda *a: (_ for _ in ()).throw(ValueError('x')))

    markdown = export.build_aggregate_portfolio_markdown(_AggregateRepo(), perf, [1, 2], 'u')

    assert perf.periods == list(export._PERF_PERIODS)
    assert '| periodo 1y | 5.00% | 4.00% |' in markdown
    # A failing Doctor read drops its sections, it does not fail the export.
    assert '## Salute del portafoglio' not in markdown
    assert '## Proiezione Monte Carlo' not in markdown


def test_aggregate_markdown_with_zero_positions(_doctor):
    markdown = export.build_aggregate_portfolio_markdown(_AggregateRepo(positions=[]), _AggregatePerformance(), [1, 2], 'u')

    assert '## Riepilogo' in markdown
    assert '| Numero posizioni | 0 |' in markdown
    assert '## Posizioni principali' not in markdown
    assert '## Migliore e peggiore di giornata' not in markdown


@pytest.mark.parametrize(('ids', 'message'), [([1, 3], MIXED_CURRENCY_MESSAGE), ([1, 42], NOT_FOUND_MESSAGE)])
def test_aggregate_markdown_propagates_scope_errors(_doctor, ids, message):
    with pytest.raises(ValueError, match=message):
        export.build_aggregate_portfolio_markdown(_AggregateRepo(), _AggregatePerformance(), ids, 'u')


def test_single_render_has_no_aggregate_header():
    markdown = render_snapshot_markdown(_full_snapshot(), 1, None)

    assert 'Vista aggregata' not in markdown
    assert '## Non inclusi nella vista aggregata' not in markdown
