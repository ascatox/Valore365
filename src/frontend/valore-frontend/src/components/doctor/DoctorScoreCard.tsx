import { forwardRef } from 'react';
import { ActionIcon, Box, Button, Group, Menu, RingProgress, Stack, Text, UnstyledButton, useMantineTheme } from '@mantine/core';
import { useClipboard } from '@mantine/hooks';
import { IconCheck, IconChevronRight, IconCopy, IconLink, IconPhoto, IconShare } from '@tabler/icons-react';
import type { PortfolioHealthResponse } from '../../services/api';

type HealthSummary = PortfolioHealthResponse['summary'];
export type DoctorFactor = keyof HealthSummary;
type Quality = 'bad' | 'mid' | 'good' | 'unknown';

const FACTORS: { key: DoctorFactor; label: string; phrase: string }[] = [
  { key: 'risk_level', label: 'Rischio', phrase: 'rischio' },
  { key: 'diversification', label: 'Diversificazione', phrase: 'diversificazione' },
  { key: 'overlap', label: 'Sovrapposizione', phrase: 'sovrapposizione tra ETF' },
  { key: 'cost_efficiency', label: 'Costi', phrase: 'costi' },
];

// How good each summary level is for the investor (higher overlap or cost is worse).
const QUALITY: Record<DoctorFactor, Record<string, Quality>> = {
  risk_level: { low: 'good', medium: 'mid', high: 'bad' },
  diversification: { excellent: 'good', good: 'good', moderate: 'mid', weak: 'bad' },
  overlap: { low: 'good', moderate: 'mid', high: 'bad' },
  cost_efficiency: { low_cost: 'good', moderate_cost: 'mid', high_cost: 'bad' },
};

const QUALITY_ORDER: Record<Quality, number> = { bad: 0, mid: 1, good: 2, unknown: 3 };

interface DoctorScoreCardProps {
  score: number;
  verdict: string;
  verdictColor: string;
  summary: HealthSummary;
  summaryLabel: (field: DoctorFactor, value: string) => string;
  privacy: boolean;
  shareSummary: string;
  shareLink: string;
  shareImageState: 'idle' | 'copying' | 'copied' | 'error';
  onShareImage: () => void;
  onFactorOpen: (factor: DoctorFactor) => void;
  onImprove: () => void;
}

/**
 * Doctor verdict: score ring, the weakest point in one line, the four factors
 * worst first with a colour for how they stand, one action. Sharing lives in a
 * menu; elements marked data-share-exclude are left out of the shared image.
 */
export const DoctorScoreCard = forwardRef<HTMLDivElement, DoctorScoreCardProps>(function DoctorScoreCard(
  {
    score,
    verdict,
    verdictColor,
    summary,
    summaryLabel,
    privacy,
    shareSummary,
    shareLink,
    shareImageState,
    onShareImage,
    onFactorOpen,
    onImprove,
  },
  ref,
) {
  const theme = useMantineTheme();
  const summaryClipboard = useClipboard({ timeout: 2000 });
  const linkClipboard = useClipboard({ timeout: 2000 });

  // The card is always dark, so colours use the dark-mode shades.
  const qualityColor: Record<Quality, string> = {
    bad: theme.colors.red[4],
    mid: theme.colors.orange[4],
    good: theme.colors.green[4],
    unknown: theme.colors.gray[5],
  };

  const factors = FACTORS
    .map((factor) => {
      const value = summary[factor.key];
      return {
        ...factor,
        value: summaryLabel(factor.key, value),
        quality: QUALITY[factor.key][value] ?? 'unknown',
      };
    })
    .sort((a, b) => QUALITY_ORDER[a.quality] - QUALITY_ORDER[b.quality]);

  const weakest = factors.find((factor) => factor.quality === 'bad' || factor.quality === 'mid');
  const copiedSomething = summaryClipboard.copied || linkClipboard.copied || shareImageState === 'copied';

  return (
    <Box
      ref={ref}
      style={{
        borderRadius: 'var(--mantine-radius-lg)',
        padding: 'var(--mantine-spacing-lg)',
        background: theme.colors.teal[9],
        color: '#ffffff',
      }}
    >
      <Group align="center" wrap="nowrap" gap="md">
        <RingProgress
          size={104}
          thickness={9}
          roundCaps
          rootColor="rgba(255,255,255,0.14)"
          sections={[{ value: privacy ? 0 : score, color: theme.colors[verdictColor]?.[4] ?? theme.colors.teal[4] }]}
          label={(
            <Stack gap={0} align="center">
              <Text fw={800} lh={1} c="white" style={{ fontSize: 30 }}>{privacy ? '••' : score}</Text>
              <Text size="xs" c="rgba(255,255,255,0.65)">su 100</Text>
            </Stack>
          )}
        />
        <Box style={{ minWidth: 0, flex: 1 }}>
          <Text fw={800} c="white" style={{ fontSize: 22, lineHeight: 1.2 }}>{verdict}</Text>
          <Text size="sm" c="rgba(255,255,255,0.8)" mt={2}>
            {weakest ? (
              <>
                {'Da migliorare: '}
                <Text span fw={700} c={qualityColor[weakest.quality]}>
                  {`${weakest.phrase} ${weakest.value.toLowerCase()}`}
                </Text>
              </>
            ) : 'Nessun punto critico nei quattro fattori.'}
          </Text>
        </Box>
        <Menu position="bottom-end" withinPortal>
          <Menu.Target>
            <ActionIcon
              data-share-exclude
              variant="outline"
              color="gray.3"
              size={40}
              radius="md"
              aria-label="Condividi il referto"
              style={{ alignSelf: 'flex-start', borderColor: 'rgba(255,255,255,0.25)' }}
              loading={shareImageState === 'copying'}
            >
              {copiedSomething ? <IconCheck size={18} /> : <IconShare size={18} />}
            </ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item leftSection={<IconCopy size={16} />} onClick={() => summaryClipboard.copy(shareSummary)}>
              {summaryClipboard.copied ? 'Riepilogo copiato' : 'Copia riepilogo'}
            </Menu.Item>
            <Menu.Item leftSection={<IconLink size={16} />} onClick={() => linkClipboard.copy(shareLink)}>
              {linkClipboard.copied ? 'Link copiato' : 'Copia link'}
            </Menu.Item>
            <Menu.Item leftSection={<IconPhoto size={16} />} onClick={onShareImage}>
              {shareImageState === 'error' ? 'Immagine non disponibile' : 'Condividi immagine'}
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>

      <Box mt="md" style={{ borderTop: '1px solid rgba(255,255,255,0.14)' }}>
        {factors.map((factor) => (
          <UnstyledButton
            key={factor.key}
            onClick={() => onFactorOpen(factor.key)}
            aria-label={`${factor.label}: ${factor.value}. Approfondisci`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              width: '100%',
              minHeight: 44,
              padding: '8px 0',
              color: '#ffffff',
              borderBottom: '1px solid rgba(255,255,255,0.14)',
            }}
          >
            <Box style={{ width: 9, height: 9, borderRadius: '50%', flexShrink: 0, background: qualityColor[factor.quality] }} />
            <Text size="sm" c="rgba(255,255,255,0.85)" style={{ flex: 1 }}>{factor.label}</Text>
            <Text size="sm" fw={700} c={qualityColor[factor.quality]}>{factor.value}</Text>
            <IconChevronRight size={16} color="rgba(255,255,255,0.4)" data-share-exclude />
          </UnstyledButton>
        ))}
      </Box>

      <Button data-share-exclude fullWidth mt="md" size="md" color="teal.6" onClick={onImprove}>
        Come migliorare
      </Button>
    </Box>
  );
});
