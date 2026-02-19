import { useState } from 'react';
import { createAsset, createAssetProviderSymbol, createTransaction } from '../../api';

const AddAsset = () => {
  const [assetName, setAssetName] = useState('');
  const [assetSymbol, setAssetSymbol] = useState('');
  const [provider, setProvider] = useState('Default');
  const [providerSymbol, setProviderSymbol] = useState('');
  const [quantity, setQuantity] = useState('');
  const [price, setPrice] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  const handleSubmit = async (e: any) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSuccessMessage('');
    setErrorMessage('');

    try {
      // 1. Create the asset
      const assetRes = await createAsset({ name: assetName, symbol: assetSymbol, class: 'Stock' });
      const assetId = assetRes.id;

      // 2. Map provider symbol to asset
      await createAssetProviderSymbol({ asset_id: assetId, provider_name: provider, symbol: providerSymbol });

      // 3. (Optional) Create a buy transaction
      if (quantity && price) {
        await createTransaction({
          asset_id: assetId,
          type: 'Buy',
          quantity: parseFloat(quantity),
          price: parseFloat(price),
          fee: 0, // Assuming no fee for simplicity
          timestamp: new Date().toISOString(),
        });
      }

      setSuccessMessage('Asset aggiunto con successo!');
      // Reset form
      setAssetName('');
      setAssetSymbol('');
      setProvider('Default');
      setProviderSymbol('');
      setQuantity('');
      setPrice('');

    } catch (error) {
      console.error(error);
      setErrorMessage('Errore durante l\'aggiunta dell\'asset.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-slate-900/50 p-6 rounded-lg border border-slate-800">
      <h2 className="text-white text-2xl font-bold mb-4">Aggiungi Titolo</h2>
      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <input
            type="text"
            placeholder="Nome (es. Apple)"
            value={assetName}
            onChange={(e) => setAssetName(e.target.value)}
            className="bg-slate-800 text-white p-2 rounded"
            required
          />
          <input
            type="text"
            placeholder="Simbolo (es. AAPL)"
            value={assetSymbol}
            onChange={(e) => setAssetSymbol(e.target.value)}
            className="bg-slate-800 text-white p-2 rounded"
            required
          />
          <input
            type="text"
            placeholder="Provider (es. Yahoo Finance)"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="bg-slate-800 text-white p-2 rounded"
            required
          />
          <input
            type="text"
            placeholder="Simbolo Provider (es. AAPL)"
            value={providerSymbol}
            onChange={(e) => setProviderSymbol(e.target.value)}
            className="bg-slate-800 text-white p-2 rounded"
            required
          />
        </div>
        <h3 className="text-white text-lg font-bold mt-6 mb-2">Aggiungi Transazione Iniziale (Opzionale)</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <input
            type="number"
            placeholder="Quantità"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            className="bg-slate-800 text-white p-2 rounded"
          />
          <input
            type="number"
            placeholder="Prezzo"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="bg-slate-800 text-white p-2 rounded"
          />
        </div>

        <button type="submit" disabled={isSubmitting} className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mt-6">
          {isSubmitting ? 'Invio...' : 'Aggiungi Titolo'}
        </button>

        {successMessage && <p className="text-green-500 mt-4">{successMessage}</p>}
        {errorMessage && <p className="text-red-500 mt-4">{errorMessage}</p>}
      </form>
    </div>
  );
};

export default AddAsset;
