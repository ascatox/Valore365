import { Badge, Group, Text, Tooltip } from '@mantine/core';
import { IconClockExclamation, IconRefresh } from '@tabler/icons-react';
import type { DoctorDataQuality } from '../../../services/api/types';
import { dataQualityLabel, formatDateTime, maskMoneyInText } from './policyFormat';

/** Freshness of the prices behind the evaluation (data_quality of the backend). */
export function FreshnessIndicator({ dataQuality, snapshotAsOf }: { dataQuality: DoctorDataQuality | null | undefined; snapshotAsOf?: string | null }) {
  if (!dataQuality) return null;
  const { label, color } = dataQualityLabel(dataQuality);
  const stale = [...(dataQuality.stale_symbols ?? []), ...(dataQuality.missing_price_symbols ?? [])];
  const Icon = dataQuality.status === 'ok' ? IconRefresh : IconClockExclamation;
  const details = [
    `Ultima sincronizzazione riuscita: ${formatDateTime(dataQuality.last_successful_price_sync)}`,
    snapshotAsOf ? `Quota più vecchia usata: ${formatDateTime(snapshotAsOf)}` : null,
    maskMoneyInText(dataQuality.note),
  ].filter(Boolean).join(' · ');
  return (
    <Group gap="xs" wrap="wrap" data-testid="doctor-freshness">
      <Tooltip label={details} multiline w={280} withArrow>
        <Badge color={color} variant="light" leftSection={<Icon size={14} aria-hidden="true" />} tabIndex={0}>
          {label}
        </Badge>
      </Tooltip>
      <Text size="xs" c="dimmed">
        {`Ultima sincronizzazione: ${formatDateTime(dataQuality.last_successful_price_sync)}`}
      </Text>
      {stale.length > 0 && (
        <Text size="xs" c="orange.8">
          {`Quote non aggiornate: ${stale.slice(0, 6).join(', ')}${stale.length > 6 ? ` e altre ${stale.length - 6}` : ''}`}
        </Text>
      )}
    </Group>
  );
}
