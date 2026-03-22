import { useState } from 'react';
import {
  Alert,
  Button,
  Drawer,
  NumberInput,
  Stack,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { upsertPortfolioTargetAllocation } from '../../../services/api';
import { AssetDiscoverSelect } from '../AssetDiscoverSelect';
import { useSwipeToClose } from '../../../hooks/useSwipeToClose';

interface TargetAllocationDrawerProps {
  opened: boolean;
  onClose: () => void;
  portfolioId: number | null;
  onSaved: () => void;
}

export function TargetAllocationDrawer({
  opened,
  onClose,
  portfolioId,
  onSaved,
}: TargetAllocationDrawerProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');
  const swipeHandlers = useSwipeToClose(onClose, { enabled: Boolean(isMobile) });
  const [resolvedAssetId, setResolvedAssetId] = useState<number | null>(null);
  const [targetWeight, setTargetWeight] = useState<number | string>(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSave = async () => {
    setError(null);
    setSuccess(null);
    const normalizedWeight = typeof targetWeight === 'number' ? targetWeight : Number(targetWeight);

    if (!portfolioId || !Number.isFinite(portfolioId)) {
      setError('Seleziona un portfolio valido');
      return;
    }
    if (!resolvedAssetId) {
      setError('Seleziona un asset dalla ricerca');
      return;
    }
    if (!Number.isFinite(normalizedWeight) || normalizedWeight < 0 || normalizedWeight > 100) {
      setError('Il peso deve essere tra 0 e 100');
      return;
    }

    try {
      setSaving(true);
      await upsertPortfolioTargetAllocation(portfolioId, {
        asset_id: resolvedAssetId,
        weight_pct: normalizedWeight,
      });
      onClose();
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore salvataggio peso');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      title="Aggiungi Asset al Portafoglio"
      position={isMobile ? 'bottom' : 'right'}
      size={isMobile ? '100%' : 'md'}
      radius={isMobile ? '24px 24px 0 0' : undefined}
      styles={{
        content: { paddingBottom: 'var(--safe-area-bottom)' },
        body: { paddingBottom: 'calc(var(--mantine-spacing-md) + var(--safe-area-bottom))' },
      }}
      onTouchStart={isMobile ? swipeHandlers.onTouchStart : undefined}
      onTouchEnd={isMobile ? swipeHandlers.onTouchEnd : undefined}
    >
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        {success && <Alert color="teal">{success}</Alert>}

        <AssetDiscoverSelect
          active={opened}
          portfolioId={portfolioId}
          onAssetResolved={(result) => {
            setResolvedAssetId(result.assetId);
            if (result.created) {
              setSuccess(`Asset creato e selezionato.`);
            }
          }}
          onClear={() => setResolvedAssetId(null)}
          onError={(msg) => setError(msg)}
        />

        <NumberInput
          label="Peso target (%)"
          value={targetWeight}
          onChange={setTargetWeight}
          min={0}
          max={100}
          decimalScale={2}
          fixedDecimalScale
          suffix="%"
        />

        <Button onClick={handleSave} loading={saving}>
          Aggiungi al Portafoglio
        </Button>
      </Stack>
    </Drawer>
  );
}
