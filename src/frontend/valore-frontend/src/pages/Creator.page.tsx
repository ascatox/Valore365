import { useState } from 'react';
import { Button, Group, Stack, Stepper } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { CreatorMethodPicker } from '../components/creator/CreatorMethodPicker';
import { CreatorModelLibrary } from '../components/creator/CreatorModelLibrary';
import { CreatorCustomize } from '../components/creator/CreatorCustomize';
import { CreatorConfirm } from '../components/creator/CreatorConfirm';
import { createPortfolio, upsertPortfolioTargetAllocation, searchAssets } from '../services/api';
import type { AllocationSlot, CreatorMethod, PortfolioModel } from '../components/creator/types';

const STEP_LABELS = ['Scegli', 'Modello', 'Personalizza', 'Conferma'];

export function CreatorPage() {
  const navigate = useNavigate();
  const isMobile = useMediaQuery('(max-width: 48em)');

  const [active, setActive] = useState(0);
  const [method, setMethod] = useState<CreatorMethod | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [slots, setSlots] = useState<AllocationSlot[]>([]);
  const [portfolioName, setPortfolioName] = useState('');
  const [creating, setCreating] = useState(false);

  /* ---- Step 1 ---- */
  const handleMethodPick = (m: CreatorMethod) => {
    setMethod(m);
    if (m === 'model') {
      setActive(1);
    }
    // profile e manual verranno gestiti nelle prossime iterazioni
  };

  /* ---- Step 2: modello selezionato ---- */
  const handleModelSelect = (model: PortfolioModel) => {
    setSelectedModelId(model.id);
    setSlots([...model.slots]);
    setPortfolioName(model.name);
  };

  /* ---- Step finale: crea portafoglio ---- */
  const handleConfirm = async () => {
    if (!portfolioName.trim() || creating) return;
    setCreating(true);

    try {
      const portfolio = await createPortfolio({
        name: portfolioName.trim(),
        base_currency: 'EUR',
        timezone: 'Europe/Rome',
      });

      // Per ogni slot, cerca l'asset tramite ticker e crea la target allocation
      for (const slot of slots) {
        if (!slot.ticker) continue;
        try {
          const results = await searchAssets(slot.ticker);
          const asset = results.find(
            (a) => a.symbol.toUpperCase() === slot.ticker!.toUpperCase(),
          ) ?? results[0];
          if (asset) {
            await upsertPortfolioTargetAllocation(portfolio.id, {
              asset_id: asset.id,
              weight_pct: slot.weight,
            });
          }
        } catch {
          // Continua con gli altri slot se un singolo asset non viene trovato
        }
      }

      window.dispatchEvent(
        new CustomEvent('valore365:portfolios-changed', { detail: { count: 1 } }),
      );
      navigate('/');
    } catch {
      // Errore gestito dal feedback visivo (il bottone smette di caricare)
    } finally {
      setCreating(false);
    }
  };

  /* ---- Navigazione stepper ---- */
  const canGoNext = () => {
    if (active === 1 && !selectedModelId) return false;
    if (active === 2) {
      const total = slots.reduce((s, sl) => s + sl.weight, 0);
      if (Math.abs(total - 100) >= 0.5) return false;
    }
    return true;
  };

  const next = () => {
    if (canGoNext() && active < STEP_LABELS.length - 1) {
      setActive((a) => a + 1);
    }
  };

  const back = () => {
    if (active === 1 && method) {
      setActive(0);
      setMethod(null);
    } else if (active > 0) {
      setActive((a) => a - 1);
    }
  };

  return (
    <PageLayout>
      <Stack gap="xl">
        <PageHeader
          eyebrow="Creator"
          title="Crea il tuo portafoglio"
          description="Scegli un modello, personalizzalo e inizia a monitorare."
        />

        <Stepper
          active={active}
          size={isMobile ? 'xs' : 'sm'}
          orientation={isMobile ? 'horizontal' : 'horizontal'}
        >
          {STEP_LABELS.map((label) => (
            <Stepper.Step key={label} label={isMobile ? undefined : label} />
          ))}
        </Stepper>

        {/* Step 0: scelta metodo */}
        {active === 0 && <CreatorMethodPicker onPick={handleMethodPick} />}

        {/* Step 1: libreria modelli */}
        {active === 1 && method === 'model' && (
          <CreatorModelLibrary
            selected={selectedModelId}
            onSelect={handleModelSelect}
          />
        )}

        {/* Step 2: personalizza */}
        {active === 2 && (
          <CreatorCustomize slots={slots} onChange={setSlots} />
        )}

        {/* Step 3: conferma */}
        {active === 3 && (
          <CreatorConfirm
            slots={slots}
            portfolioName={portfolioName}
            onNameChange={setPortfolioName}
            onConfirm={handleConfirm}
            loading={creating}
          />
        )}

        {/* Navigazione */}
        {active > 0 && (
          <Group justify="space-between">
            <Button variant="default" onClick={back}>
              Indietro
            </Button>
            {active < STEP_LABELS.length - 1 && (
              <Button onClick={next} disabled={!canGoNext()}>
                Avanti
              </Button>
            )}
          </Group>
        )}
      </Stack>
    </PageLayout>
  );
}
