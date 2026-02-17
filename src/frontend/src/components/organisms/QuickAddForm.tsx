import { useEffect, useState, type FormEvent } from "react";

import { createAsset, createAssetProviderSymbol, createTransaction, searchAssets } from "../../api";
import type { AssetSearchItem, AssetType } from "../../types";
import Button from "../atoms/Button";
import Panel from "../atoms/Panel";
import type { ToastKind } from "../feedback/toast-types";

type QuickAddFormProps = {
  portfolioId: number;
  getAccessToken: () => Promise<string>;
  onToast: (kind: ToastKind, message: string) => void;
  onCompleted: () => Promise<void>;
};

function QuickAddForm({ portfolioId, getAccessToken, onToast, onCompleted }: QuickAddFormProps) {
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [symbol, setSymbol] = useState<string>("");
  const [name, setName] = useState<string>("");
  const [assetType, setAssetType] = useState<AssetType>("stock");
  const [exchangeCode, setExchangeCode] = useState<string>("");
  const [exchangeName, setExchangeName] = useState<string>("");
  const [quoteCurrency, setQuoteCurrency] = useState<string>("USD");
  const [isin, setIsin] = useState<string>("");
  const [providerSymbol, setProviderSymbol] = useState<string>("");
  const [autoBuy, setAutoBuy] = useState<boolean>(true);
  const [buyQuantity, setBuyQuantity] = useState<string>("1");
  const [buyPrice, setBuyPrice] = useState<string>("0");
  const [assetSuggestions, setAssetSuggestions] = useState<AssetSearchItem[]>([]);
  const [selectedExistingAsset, setSelectedExistingAsset] = useState<AssetSearchItem | null>(null);

  useEffect(() => {
    const q = symbol.trim();
    if (!q || q.length < 1 || selectedExistingAsset) {
      setAssetSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const token = await getAccessToken();
        const items = await searchAssets(q, token);
        setAssetSuggestions(items.slice(0, 6));
      } catch {
        setAssetSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [getAccessToken, symbol, selectedExistingAsset]);

  function validateQuickAdd(): string | null {
    const symbolValue = symbol.trim().toUpperCase();
    const quoteCurrencyValue = quoteCurrency.trim().toUpperCase();
    const isinValue = isin.trim().toUpperCase();
    const exchangeCodeValue = exchangeCode.trim().toUpperCase();

    if (!selectedExistingAsset && !/^[A-Z0-9.\-]{1,32}$/.test(symbolValue)) {
      return "Symbol non valido (usa lettere/numeri, max 32).";
    }
    if (!/^[A-Z]{3}$/.test(quoteCurrencyValue)) {
      return "Quote CCY non valida (formato ISO a 3 lettere).";
    }
    if (isinValue && !/^[A-Z0-9]{12}$/.test(isinValue)) {
      return "ISIN non valido (12 caratteri alfanumerici).";
    }
    if (exchangeCodeValue && !/^[A-Z0-9]{1,16}$/.test(exchangeCodeValue)) {
      return "Exchange code non valido (max 16 alfanumerici).";
    }
    if (autoBuy) {
      const qty = Number(buyQuantity);
      const price = Number(buyPrice);
      if (!(qty > 0)) {
        return "Qty Buy deve essere maggiore di zero.";
      }
      if (!(price >= 0)) {
        return "Price Buy non valido.";
      }
    }
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const validationError = validateQuickAdd();
    if (validationError) {
      onToast("error", validationError);
      return;
    }

    const normalizedSymbol = symbol.trim().toUpperCase();
    const normalizedQuoteCurrency = quoteCurrency.trim().toUpperCase();
    const normalizedProviderSymbol = (providerSymbol.trim() || normalizedSymbol).toUpperCase();

    setSubmitting(true);
    try {
      const token = await getAccessToken();
      let assetId: number;
      let assetLabel: string;

      if (selectedExistingAsset) {
        assetId = Number(selectedExistingAsset.id);
        assetLabel = selectedExistingAsset.symbol;
      } else {
        const asset = await createAsset(
          {
            symbol: normalizedSymbol,
            name: name.trim() || undefined,
            asset_type: assetType,
            exchange_code: exchangeCode.trim().toUpperCase() || undefined,
            exchange_name: exchangeName.trim() || undefined,
            quote_currency: normalizedQuoteCurrency,
            isin: isin.trim().toUpperCase() || undefined,
            active: true,
          },
          token
        );

        await createAssetProviderSymbol(
          {
            asset_id: asset.id,
            provider: "twelvedata",
            provider_symbol: normalizedProviderSymbol,
          },
          token
        );

        assetId = asset.id;
        assetLabel = asset.symbol;
      }

      if (autoBuy) {
        const qty = Number(buyQuantity);
        const price = Number(buyPrice);
        await createTransaction(
          {
            portfolio_id: portfolioId,
            asset_id: assetId,
            side: "buy",
            trade_at: new Date().toISOString(),
            quantity: qty,
            price,
            fees: 0,
            taxes: 0,
            trade_currency: normalizedQuoteCurrency,
            notes: "Quick add from frontend",
          },
          token
        );
      }

      onToast("success", `Titolo ${assetLabel} inserito con successo.`);
      setSymbol("");
      setName("");
      setExchangeCode("");
      setExchangeName("");
      setIsin("");
      setProviderSymbol("");
      setSelectedExistingAsset(null);
      setAssetSuggestions([]);
      await onCompleted();
    } catch (e) {
      onToast("error", e instanceof Error ? e.message : "Errore inserimento titolo");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Panel title="Aggiungi Titolo Rapido">
      <form className="quick-form" onSubmit={handleSubmit}>
        <label className="suggestion-host">
          Symbol*
          <input
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value);
              setSelectedExistingAsset(null);
            }}
            placeholder="AAPL"
            required
          />
          {assetSuggestions.length > 0 && !selectedExistingAsset && (
            <div className="suggestions">
              {assetSuggestions.map((item) => (
                <button
                  key={`${item.id}-${item.symbol}`}
                  type="button"
                  className="suggestion-item"
                  onClick={() => {
                    setSelectedExistingAsset(item);
                    setSymbol(item.symbol);
                    setName(item.name ?? "");
                    setProviderSymbol(item.symbol);
                    setAssetSuggestions([]);
                  }}
                >
                  <span>{item.symbol}</span>
                  <small>{item.name}</small>
                </button>
              ))}
            </div>
          )}
        </label>
        <label>
          Nome
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Apple Inc." />
        </label>
        <label>
          Tipo
          <select value={assetType} onChange={(e) => setAssetType(e.target.value as AssetType)} disabled={!!selectedExistingAsset}>
            <option value="stock">stock</option>
            <option value="etf">etf</option>
            <option value="crypto">crypto</option>
            <option value="bond">bond</option>
            <option value="cash">cash</option>
            <option value="fund">fund</option>
          </select>
        </label>
        <label>
          Quote CCY*
          <input value={quoteCurrency} onChange={(e) => setQuoteCurrency(e.target.value)} placeholder="USD" required />
        </label>
        <label>
          Exchange Code
          <input value={exchangeCode} onChange={(e) => setExchangeCode(e.target.value)} placeholder="XNAS" disabled={!!selectedExistingAsset} />
        </label>
        <label>
          Provider Symbol
          <input value={providerSymbol} onChange={(e) => setProviderSymbol(e.target.value)} placeholder="AAPL" disabled={!!selectedExistingAsset} />
        </label>
        <label>
          Exchange Name
          <input value={exchangeName} onChange={(e) => setExchangeName(e.target.value)} placeholder="NASDAQ" disabled={!!selectedExistingAsset} />
        </label>
        <label>
          ISIN
          <input value={isin} onChange={(e) => setIsin(e.target.value)} placeholder="US0378331005" disabled={!!selectedExistingAsset} />
        </label>

        <label className="checkbox-row">
          <input type="checkbox" checked={autoBuy} onChange={(e) => setAutoBuy(e.target.checked)} />
          Crea anche acquisto iniziale
        </label>
        <label>
          Qty Buy
          <input value={buyQuantity} onChange={(e) => setBuyQuantity(e.target.value)} type="number" step="0.0001" min="0" />
        </label>
        <label>
          Price Buy
          <input value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} type="number" step="0.0001" min="0" />
        </label>

        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? "Inserimento..." : selectedExistingAsset ? "Aggiungi Posizione" : "Aggiungi Titolo"}
        </Button>
      </form>
      {selectedExistingAsset && (
        <p className="hint">
          Usando titolo gia presente: {selectedExistingAsset.symbol} ({selectedExistingAsset.name})
        </p>
      )}
    </Panel>
  );
}

export default QuickAddForm;
