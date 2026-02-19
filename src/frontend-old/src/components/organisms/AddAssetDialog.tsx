
import * as React from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Input } from "@/components/ui/input"
import { LucidePlus } from "lucide-react"

// Mocking the search API result and asset details
const MOCK_SEARCH_RESULTS = [
    { ticker: 'VWCE', name: 'Vanguard FTSE All-World UCITS ETF', lastPrice: 110.50 },
    { ticker: 'AAPL', name: 'Apple Inc.', lastPrice: 172.25 },
    { ticker: 'MSFT', name: 'Microsoft Corporation', lastPrice: 429.34 },
    { ticker: 'SPY', name: 'SPDR S&P 500 ETF TRUST', lastPrice: 512.18 },
    { ticker: 'AGGH', name: 'iShares Global Aggregate Bond UCITS ETF', lastPrice: 5.35 },
];

type MockAsset = (typeof MOCK_SEARCH_RESULTS)[0];

export function AddAssetDialog() {
  const [open, setOpen] = React.useState(false);
  const [step, setStep] = React.useState<'search' | 'details'>('search');
  const [selectedAsset, setSelectedAsset] = React.useState<MockAsset | null>(null);
  const [quantity, setQuantity] = React.useState("");
  const [avgPrice, setAvgPrice] = React.useState("");

  // This effect resets the form when the dialog is closed
  React.useEffect(() => {
    if (!open) {
      setTimeout(() => {
        setStep('search');
        setSelectedAsset(null);
        setQuantity("");
        setAvgPrice("");
      }, 200); // Give it a moment to avoid content flicker while closing
    }
  }, [open]);

  const handleSelectAsset = (asset: MockAsset) => {
    setSelectedAsset(asset);
    setStep('details');
  }

  const handleSubmit = () => {
    console.log("POST /assets", {
        ticker: selectedAsset?.ticker,
        quantity: parseFloat(quantity),
        avg_price: parseFloat(avgPrice)
    });
    
    // In a real app, you would show a toast here, e.g. using react-hot-toast or similar
    // toast.success("Asset aggiunto con successo!");

    setOpen(false);
  }
  
  const estimatedValue = selectedAsset && quantity ? parseFloat(quantity) * selectedAsset.lastPrice : 0;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="bg-indigo-600 hover:bg-indigo-700 text-white">
          <LucidePlus className="mr-2 h-4 w-4" />
          Aggiungi Asset
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[480px] bg-slate-900 border-slate-800 text-white">
        <DialogHeader>
          <DialogTitle>
            {step === 'search' ? 'Cerca un asset' : `Aggiungi ${selectedAsset?.ticker}`}
          </DialogTitle>
          <DialogDescription className="text-slate-400">
            {step === 'search' 
              ? "Cerca per ticker o nome nel nostro database."
              : `Inserisci i dettagli della tua posizione in ${selectedAsset?.name}.`
            }
          </DialogDescription>
        </DialogHeader>

        {step === 'search' && (
          <Command className="bg-slate-900 rounded-lg">
            <CommandInput placeholder="Es: VWCE, Apple, ..." />
            <CommandList>
              <CommandEmpty>Nessun asset trovato.</CommandEmpty>
              <CommandGroup heading="Risultati">
                {MOCK_SEARCH_RESULTS.map((asset) => (
                  <CommandItem
                    key={asset.ticker}
                    onSelect={() => handleSelectAsset(asset)}
                    className="cursor-pointer hover:bg-slate-800"
                  >
                    <div className="flex justify-between w-full">
                      <div className="flex flex-col">
                        <span className="font-bold text-white">{asset.ticker}</span>
                        <span className="text-sm text-slate-400">{asset.name}</span>
                      </div>
                      <span className="font-mono text-white my-auto">
                        {new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(asset.lastPrice)}
                      </span>
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        )}

        {step === 'details' && selectedAsset && (
          <div className="grid gap-4 pt-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <label htmlFor="quantity" className="text-right text-sm text-slate-400">
                Quantità
              </label>
              <Input
                id="quantity"
                type="number"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="Es: 150.5"
                className="col-span-3 bg-slate-800 border-slate-700 text-white font-mono"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <label htmlFor="avgPrice" className="text-right text-sm text-slate-400">
                Prezzo Medio
              </label>
              <Input
                id="avgPrice"
                type="number"
                value={avgPrice}
                onChange={(e) => setAvgPrice(e.target.value)}
                placeholder="Es: 95.50"
                className="col-span-3 bg-slate-800 border-slate-700 text-white font-mono"
              />
            </div>
            {estimatedValue > 0 && (
                <div className="text-center text-sm text-slate-400 mt-2 bg-slate-800/50 rounded-md p-2">
                    Controvalore stimato:
                    <span className="font-mono text-white ml-2">
                        {new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(estimatedValue)}
                    </span>
                </div>
            )}
          </div>
        )}

        {step === 'details' && (
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setStep('search')} className="text-white border-slate-700 hover:bg-slate-800">
              Indietro
            </Button>
            <Button onClick={handleSubmit} className="bg-indigo-600 hover:bg-indigo-700 text-white" disabled={!quantity || !avgPrice}>
              Salva Posizione
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
