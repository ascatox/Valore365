-- 1. Cancella tutte le transazioni                                                                                                                                       
  DELETE FROM transactions;                                                                                                                                                 
   
  -- 2. Cancella i batch di import CSV (opzionale, per pulizia)                                                                                                             
  DELETE FROM csv_import_batches;           

  delete from assets  ;        

  delete from portfolios;    

  delete from portfolio_target_allocations;

  -- 3. Verifica
  SELECT count(*) AS remaining_transactions FROM transactions;
  SELECT count(*) AS remaining_batches FROM csv_import_batches;