-- Verifica quali righe hanno NaN/Inf in price_bars_1d                                                                                                                                                                         
  SELECT asset_id, price_date, close, provider                                                                                                                                                                                 
  FROM price_bars_1d                                                                                                                                                                                                             
  WHERE close = 'NaN' OR close = 'Infinity' OR close = '-Infinity';                                                                                                                                                              

  -- Elimina le righe con valori corrotti
  DELETE FROM price_bars_1d
  WHERE close = 'NaN' OR close = 'Infinity' OR close = '-Infinity';