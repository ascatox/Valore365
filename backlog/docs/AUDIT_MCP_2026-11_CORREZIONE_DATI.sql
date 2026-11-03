-- =====================================================================
-- Audit MCP 2026-11 — Correzione dei dati di Wealth (portafoglio 26)
-- PARTE A: 39 acquisti con prezzo ×1000 e quantità ÷1000 (TASK-41, V365-008)
--
-- Causa: import XLSX del 2026-03-17 (batch 30, "Lista Titoli (9).xlsx"),
-- prima del fix del parser (commit b655330). I prezzi con esattamente 3
-- decimali sono stati letti con il punto come separatore delle migliaia, e
-- la quantità è stata ricalcolata come controvalore / prezzo.
-- Correzione: prezzo / 1000 e quantità × 1000. Il controvalore (quantità ×
-- prezzo) e le commissioni restano identici.
--
-- COME USARLO (Supabase > SQL Editor):
--   1. Esegui il PASSO 1 (sola lettura) e controlla le 39 righe.
--   2. Esegui il PASSO 2 (copia di sicurezza in una tabella separata).
--   3. Esegui il PASSO 3: applica la modifica e mostra il risultato, ma
--      termina con ROLLBACK, quindi non salva niente.
--   4. Se il risultato del PASSO 3 è corretto, rieseguilo sostituendo
--      l'ultima riga "rollback;" con "commit;".
-- Per annullare dopo il commit c'è il PASSO 4, che usa la copia di sicurezza.
-- =====================================================================


-- ---------------------------------------------------------------------
-- PASSO 1 — Anteprima (sola lettura). Attese: 39 righe, tutte del portafoglio 26.
-- ---------------------------------------------------------------------
begin transaction read only;
select t.id, a.symbol, t.trade_at::date as data,
       t.quantity as quantita_attuale, t.price as prezzo_attuale,
       t.quantity * 1000 as quantita_nuova, t.price / 1000 as prezzo_nuovo,
       round(t.quantity * t.price, 2) as controvalore_invariato
from transactions t join assets a on a.id = t.asset_id
where t.portfolio_id = 26 and t.side = 'buy'
  and t.id in (5755,5665,5659,5629,5581,5693,5652,5632,5618,5559,
               5759,5745,5648,5596,5564,5718,5711,5704,5694,5671,
               5649,5614,5599,5560,5529,5489,5684,5584,5635,5540,
               5664,5651,5620,5604,5583,5579,5784,5610,5595)
  and t.price >= 1000 and t.quantity < 0.1
order by a.symbol, t.trade_at;
rollback;


-- ---------------------------------------------------------------------
-- PASSO 2 — Copia di sicurezza delle righe che verranno modificate.
-- Crea una tabella separata e non modifica le transazioni.
-- ---------------------------------------------------------------------
create table if not exists backup_tx_fix_x1000_20261103 as
select * from transactions
where portfolio_id = 26 and side = 'buy'
  and id in (5755,5665,5659,5629,5581,5693,5652,5632,5618,5559,
             5759,5745,5648,5596,5564,5718,5711,5704,5694,5671,
             5649,5614,5599,5560,5529,5489,5684,5584,5635,5540,
             5664,5651,5620,5604,5583,5579,5784,5610,5595)
  and price >= 1000 and quantity < 0.1;

select count(*) as righe_in_backup from backup_tx_fix_x1000_20261103;  -- attese: 39


-- ---------------------------------------------------------------------
-- PASSO 3 — Correzione. Finisce con ROLLBACK: per salvare, sostituisci
-- l'ultima riga con COMMIT, solo dopo aver controllato il risultato.
-- ---------------------------------------------------------------------
begin;

update transactions t
set price = t.price / 1000,
    quantity = t.quantity * 1000
from backup_tx_fix_x1000_20261103 b
where t.id = b.id
  and t.price = b.price and t.quantity = b.quantity;  -- solo se la riga non è cambiata nel frattempo

-- Verifica 1: 39 righe corrette, controvalore identico al backup.
select t.id, b.price as prezzo_prima, t.price as prezzo_dopo,
       b.quantity as quantita_prima, t.quantity as quantita_dopo,
       round(b.quantity * b.price, 4) = round(t.quantity * t.price, 4) as controvalore_uguale
from transactions t join backup_tx_fix_x1000_20261103 b on b.id = t.id
order by t.id;

-- Verifica 2: nessun prezzo anomalo rimasto in Wealth (attese: 0 righe).
with med as (
  select asset_id, percentile_cont(0.5) within group (order by price) as mediana
  from transactions where side in ('buy','sell') and asset_id is not null group by asset_id
)
select t.id, t.price from transactions t join med m on m.asset_id = t.asset_id
where t.portfolio_id = 26 and t.side in ('buy','sell') and t.price > 500 * m.mediana;

-- Verifica 3: nuove quantità per strumento in Wealth (da confrontare con il broker).
select a.symbol,
       sum(case when t.side = 'buy' then t.quantity when t.side = 'sell' then -t.quantity else 0 end) as quantita
from transactions t join assets a on a.id = t.asset_id
where t.portfolio_id = 26 and t.side in ('buy','sell')
  and a.symbol in ('DBXP.DE','EQQQ.DE','EUN5.DE','FRC3.DE','IBTM.L','IEVL.L','IHYG.L','SE15.L','VWRA.L')
group by a.symbol order by a.symbol;

rollback;   -- <-- sostituisci con "commit;" per salvare


-- ---------------------------------------------------------------------
-- PASSO 4 — Annullamento (solo se serve dopo il commit): ripristina i
-- valori originali dalla copia di sicurezza.
-- ---------------------------------------------------------------------
-- begin;
-- update transactions t set price = b.price, quantity = b.quantity
-- from backup_tx_fix_x1000_20261103 b where t.id = b.id;
-- commit;


-- =====================================================================
-- PARTE B: duplicati dell'import del 2026-10-23 (TASK-42) — da preparare
-- dopo l'elenco completo degli id 5790–5870.
-- =====================================================================
