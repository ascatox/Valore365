select asset_id, expense_ratio, fund_family, total_assets, category,
       sector, industry, country, market_cap,
       trailing_pe, forward_pe, dividend_yield, dividend_rate,
       beta, fifty_two_week_high, fifty_two_week_low, avg_volume,
       profit_margins, return_on_equity, revenue_growth, earnings_growth,
       description, website, logo_url, raw_info, updated_at
from asset_metadata
where asset_id = :asset_id
