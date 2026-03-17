INSERT INTO etf_enrichment (
    asset_id, isin, name, description, index_tracked, investment_focus,
    country_weights, sector_weights, top_holdings, holdings_date,
    replication_method, distribution_policy, distribution_frequency,
    fund_currency, currency_hedged, domicile, fund_provider,
    fund_size_eur, ter, volatility_1y, sustainability, inception_date,
    source, fetched_at
) VALUES (
    :asset_id, :isin, :name, :description, :index_tracked, :investment_focus,
    :country_weights::jsonb, :sector_weights::jsonb, :top_holdings::jsonb, :holdings_date,
    :replication_method, :distribution_policy, :distribution_frequency,
    :fund_currency, :currency_hedged, :domicile, :fund_provider,
    :fund_size_eur, :ter, :volatility_1y, :sustainability, :inception_date,
    :source, now()
)
ON CONFLICT (asset_id) DO UPDATE SET
    isin = EXCLUDED.isin,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    index_tracked = EXCLUDED.index_tracked,
    investment_focus = EXCLUDED.investment_focus,
    country_weights = EXCLUDED.country_weights,
    sector_weights = EXCLUDED.sector_weights,
    top_holdings = EXCLUDED.top_holdings,
    holdings_date = EXCLUDED.holdings_date,
    replication_method = EXCLUDED.replication_method,
    distribution_policy = EXCLUDED.distribution_policy,
    distribution_frequency = EXCLUDED.distribution_frequency,
    fund_currency = EXCLUDED.fund_currency,
    currency_hedged = EXCLUDED.currency_hedged,
    domicile = EXCLUDED.domicile,
    fund_provider = EXCLUDED.fund_provider,
    fund_size_eur = EXCLUDED.fund_size_eur,
    ter = EXCLUDED.ter,
    volatility_1y = EXCLUDED.volatility_1y,
    sustainability = EXCLUDED.sustainability,
    inception_date = EXCLUDED.inception_date,
    source = EXCLUDED.source,
    fetched_at = now()
