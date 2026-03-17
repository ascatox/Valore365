SELECT asset_id, isin, name, description, index_tracked, investment_focus,
       country_weights, sector_weights, top_holdings, holdings_date,
       replication_method, distribution_policy, distribution_frequency,
       fund_currency, currency_hedged, domicile, fund_provider,
       fund_size_eur, ter, volatility_1y, sustainability, inception_date,
       source, fetched_at
FROM etf_enrichment
WHERE asset_id = :asset_id
