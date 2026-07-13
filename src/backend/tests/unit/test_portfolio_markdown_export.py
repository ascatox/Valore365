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
    performance_rows = [['1 anno', '5.00%', '4.80%', '5.00%', '4.80%', '9 000.00', '500.00']]

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
