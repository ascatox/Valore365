-- =====================================================================
-- Audit MCP 2026-11 — Query di verifica sui dati (SOLA LETTURA)
-- Task: TASK-41 (V365-008, costo di carico SE15/IBTM) e TASK-42 (V365-009, dividendi ripetuti)
--
-- Come usarle:
--   * Supabase > SQL Editor. Esegui UNA query alla volta ed esporta il risultato (CSV o copia).
--   * Sono tutte SELECT: non modificano nulla. Per sicurezza ogni blocco gira in una
--     transazione READ ONLY che termina con ROLLBACK.
--   * Portafogli: 19 = Parent, 26 = Wealth (dall'audit). Se gli id sono diversi, cambiali nei filtri.
--   * Prima di condividere i risultati puoi oscurare le note se contengono dati personali.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q1. Anagrafica degli strumenti quotati a Londra (.L) e di SE15/IBTM
--     Scopo: verificare valuta di quotazione (quote_currency), ISIN, borsa
--     e simbolo usato dal provider dei prezzi.
-- ---------------------------------------------------------------------
begin transaction read only;
select a.id, a.symbol, a.name, a.isin, a.asset_type, a.exchange_code, a.exchange_name,
       a.quote_currency,
       string_agg(aps.provider || ':' || aps.provider_symbol, ', ') as provider_symbols
from assets a
left join asset_provider_symbols aps on aps.asset_id = a.id
where a.symbol ilike '%.L' or a.symbol ilike 'SE15%' or a.symbol ilike 'IBTM%'
   or a.exchange_code in ('LSE','L','LON')
group by a.id
order by a.symbol;
rollback;


-- ---------------------------------------------------------------------
-- Q2. Ultimi prezzi giornalieri di SE15 e IBTM
--     Scopo: capire se i prezzi sono in GBP, GBp (pence, ~100 volte più grandi)
--     o USD, e confrontarli con i prezzi delle transazioni.
-- ---------------------------------------------------------------------
begin transaction read only;
select a.symbol, a.quote_currency, b.provider, b.price_date, b.close
from price_bars_1d b
join assets a on a.id = b.asset_id
where a.symbol ilike 'SE15%' or a.symbol ilike 'IBTM%'
order by a.symbol, b.price_date desc
limit 40;
rollback;


-- ---------------------------------------------------------------------
-- Q3. Registro dei lotti di SE15 e IBTM nei portafogli 19 e 26
--     Scopo: ricostruire quantità, prezzo, valuta, cambio usato e quantità
--     progressiva per ogni operazione, per riconciliare il costo medio.
--     Controlla: fx_usato vuoto (il codice usa 1.0 al suo posto), prezzo fuori
--     dal range di mercato, quantita_progressiva negativa, "Cambio:" nelle note
--     diverso da fx_usato.
-- ---------------------------------------------------------------------
begin transaction read only;
select t.portfolio_id, t.id, a.symbol, t.side, t.trade_at::date as data,
       t.quantity, t.price, t.fees, t.taxes, t.trade_currency,
       a.quote_currency, p.base_currency,
       case when t.trade_currency = p.base_currency then 1
            else (select f.rate from fx_rates_1d f
                  where f.from_ccy = t.trade_currency and f.to_ccy = p.base_currency
                    and f.price_date <= t.trade_at::date
                  order by f.price_date desc limit 1)
       end as fx_usato,
       t.quantity * t.price as controvalore_valuta_trade,
       sum(case when t.side = 'buy' then t.quantity else -t.quantity end)
         over (partition by t.portfolio_id, t.asset_id order by t.trade_at, t.id) as quantita_progressiva,
       t.notes
from transactions t
join assets a on a.id = t.asset_id
join portfolios p on p.id = t.portfolio_id
where t.portfolio_id in (19, 26)
  and (a.symbol ilike 'SE15%' or a.symbol ilike 'IBTM%')
  and t.side in ('buy', 'sell')
order by t.portfolio_id, a.symbol, t.trade_at, t.id;
rollback;


-- ---------------------------------------------------------------------
-- Q4. Operazioni in valuta estera senza tasso di cambio disponibile
--     Scopo: trovare le transazioni per cui il calcolo del costo usa in
--     silenzio un cambio pari a 1.0.
-- ---------------------------------------------------------------------
begin transaction read only;
select t.portfolio_id, a.symbol, t.trade_currency, p.base_currency,
       count(*) as transazioni, min(t.trade_at::date) as dal, max(t.trade_at::date) as al
from transactions t
join portfolios p on p.id = t.portfolio_id
left join assets a on a.id = t.asset_id
where t.portfolio_id in (19, 26)
  and t.trade_currency <> p.base_currency
  and not exists (
    select 1 from fx_rates_1d f
    where f.from_ccy = t.trade_currency and f.to_ccy = p.base_currency
      and f.price_date <= t.trade_at::date)
group by t.portfolio_id, a.symbol, t.trade_currency, p.base_currency
order by t.portfolio_id, a.symbol;
rollback;


-- ---------------------------------------------------------------------
-- Q5. Strumenti in portafoglio con valuta di quotazione uguale alla valuta
--     del portafoglio ma quotati su borse non in euro
--     Scopo: misurare quanti asset potrebbero avere quote_currency sbagliata
--     (il codice la imposta alla valuta del portafoglio quando crea l'asset).
-- ---------------------------------------------------------------------
begin transaction read only;
select distinct a.id, a.symbol, a.name, a.exchange_code, a.quote_currency, p.base_currency
from transactions t
join assets a on a.id = t.asset_id
join portfolios p on p.id = t.portfolio_id
where t.portfolio_id in (19, 26)
  and a.quote_currency = p.base_currency
  and (a.symbol ~* '\.(L|SW|TO|AX|HK|T)$'
       or (a.symbol !~ '\.' and a.asset_type in ('stock', 'etf')))
order by a.symbol;
rollback;


-- ---------------------------------------------------------------------
-- Q6. Transazioni con attributi identici (possibili duplicati)
--     Scopo: elencare i gruppi di righe uguali per portafoglio, strumento,
--     tipo, data, quantità, prezzo, costi e valuta. NON significa che siano
--     duplicati: due pagamenti reali possono essere identici. Gli id e le note
--     servono a capirlo (id molto distanti = inseriti in momenti diversi).
-- ---------------------------------------------------------------------
begin transaction read only;
select t.portfolio_id, a.symbol, t.side, t.trade_at::date as data,
       t.quantity, t.price, t.fees, t.taxes, t.trade_currency,
       count(*) as righe,
       array_agg(t.id order by t.id) as ids,
       array_agg(distinct coalesce(t.notes, '')) as note_distinte
from transactions t
left join assets a on a.id = t.asset_id
where t.portfolio_id in (19, 26)
group by t.portfolio_id, a.symbol, t.side, t.trade_at::date,
         t.quantity, t.price, t.fees, t.taxes, t.trade_currency
having count(*) > 1
order by righe desc, t.portfolio_id, data desc;
rollback;


-- ---------------------------------------------------------------------
-- Q7. Batch di import dei portafogli 19 e 26
--     Scopo: vedere se lo stesso file è stato importato più volte, o se un
--     batch è stato confermato con righe già presenti.
-- ---------------------------------------------------------------------
begin transaction read only;
select b.portfolio_id, b.id, b.status, b.original_filename, b.total_rows, b.valid_rows,
       b.error_rows, b.created_at, b.committed_at,
       count(*) over (partition by b.portfolio_id, b.original_filename) as stesso_file_n_volte
from csv_import_batches b
where b.portfolio_id in (19, 26)
order by b.portfolio_id, b.created_at;
rollback;


-- ---------------------------------------------------------------------
-- Q8. Dividendi per valuta (portafoglio 26)
--     Scopo: verificare se ci sono dividendi in valute diverse, che il tool
--     get_dividend_summary oggi somma senza conversione.
-- ---------------------------------------------------------------------
begin transaction read only;
select t.trade_currency, count(*) as righe,
       sum(t.quantity * t.price) as importo_lordo, sum(t.taxes) as ritenute,
       min(t.trade_at::date) as dal, max(t.trade_at::date) as al
from transactions t
where t.portfolio_id = 26 and t.side = 'dividend'
group by t.trade_currency
order by righe desc;
rollback;


-- ---------------------------------------------------------------------
-- Q9. Righe con prezzo gonfiato ×1000 (bug di import dei prezzi a 3 decimali)
--     Tutti i portafogli. Una riga è sospetta se il suo prezzo è più di 500
--     volte la mediana dei prezzi dello stesso strumento.
-- ---------------------------------------------------------------------
begin transaction read only;
with med as (
  select asset_id, percentile_cont(0.5) within group (order by price) as mediana
  from transactions where side in ('buy','sell') and asset_id is not null
  group by asset_id
)
select t.portfolio_id, t.id, a.symbol, t.side, t.trade_at::date as data,
       t.quantity, t.price, t.quantity * t.price as controvalore,
       t.price / 1000 as prezzo_corretto, t.quantity * 1000 as quantita_corretta
from transactions t
join med m on m.asset_id = t.asset_id
join assets a on a.id = t.asset_id
where t.side in ('buy','sell') and t.price > 500 * m.mediana
order by t.portfolio_id, a.symbol, t.trade_at;
rollback;
