insert into portfolios (name, base_currency, timezone)
values ('Valore365 Portfolio', 'EUR', 'Europe/Rome')
on conflict do nothing;

insert into assets (symbol, name, asset_type, exchange_code, exchange_name, quote_currency, isin, active)
values
  ('AAPL', 'Apple Inc.', 'stock', 'XNAS', 'NASDAQ', 'USD', 'US0378331005', true),
  ('MSFT', 'Microsoft Corporation', 'stock', 'XNAS', 'NASDAQ', 'USD', 'US5949181045', true),
  ('VWCE', 'Vanguard FTSE All-World UCITS ETF', 'etf', 'XMIL', 'Borsa Italiana', 'EUR', 'IE00BK5BQT80', true)
on conflict (symbol, exchange_code) do update
set
  name = excluded.name,
  asset_type = excluded.asset_type,
  exchange_name = excluded.exchange_name,
  quote_currency = excluded.quote_currency,
  isin = excluded.isin,
  active = excluded.active;

insert into asset_provider_symbols (asset_id, provider, provider_symbol)
select id,
       'yfinance',
       case symbol
           when 'VWCE' then 'VWCE.MI'
           else symbol
       end
from assets
where symbol in ('AAPL', 'MSFT', 'VWCE')
on conflict (asset_id, provider) do update
set provider_symbol = excluded.provider_symbol;
