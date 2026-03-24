import { describe, expect, it } from 'vitest';
import { recommendPortfolioModels } from './models';

describe('recommendPortfolioModels', () => {
  it('prefers defensive models for prudent profiles', () => {
    const recommendations = recommendPortfolioModels({
      horizon: 'lt5',
      riskTolerance: 'sell_all',
      objective: 'capital_preservation',
    });

    expect(recommendations).toHaveLength(2);
    expect(['all-weather', 'permanent-portfolio', 'golden-butterfly']).toContain(
      recommendations[0]?.model.id,
    );
  });

  it('prefers growth-oriented models for aggressive profiles', () => {
    const recommendations = recommendPortfolioModels({
      horizon: 'gt20',
      riskTolerance: 'buy_more',
      objective: 'max_growth',
    });

    expect(recommendations).toHaveLength(2);
    expect(['aggressive-80-20', 'full-equity']).toContain(recommendations[0]?.model.id);
  });
});
