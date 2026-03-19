import { useState } from 'react';
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Card,
  Collapse,
  Group,
  Loader,
  Progress,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
  UnstyledButton,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconAlertTriangle, IconChevronDown, IconChevronRight, IconInfoCircle, IconSearch } from '@tabler/icons-react';
import { usePortfolioXray } from '../dashboard/hooks/queries';
import { STORAGE_KEYS } from '../dashboard/constants';
import { AssetInfoModal } from '../dashboard/holdings/AssetInfoModal';
import type { XRayEtfDetail, XRayHolding } from '../../services/api';
import { formatXrayFailureReason } from '../../services/dataQuality';

const PRIVACY_MASK = '******';

function isPrivacyModeEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled) === 'true';
}

function getHoldingsSourceTone(detail: XRayEtfDetail): { color: string; label: string } {
  if (detail.holdings_source === 'justetf') return { color: 'teal', label: 'justETF' };
  if (detail.holdings_source === 'yfinance') return { color: 'blue', label: 'fallback yfinance' };
  return { color: 'orange', label: 'copertura assente' };
}

interface Props {
  portfolioId: number | null;
}

/* ---- Clickable ETF badge ---- */
function EtfBadge({ symbol, onClick }: { symbol: string; onClick: (symbol: string) => void }) {
  return (
    <Tooltip label={`Dettaglio ${symbol}`} withArrow>
      <Badge
        size="xs"
        variant="light"
        color="indigo"
        style={{ cursor: 'pointer' }}
        onClick={(e) => { e.stopPropagation(); onClick(symbol); }}
      >
        {symbol}
      </Badge>
    </Tooltip>
  );
}

/* ---- Mobile card for a single aggregated holding ---- */
function HoldingCard({
  holding,
  rank,
  privacy,
  isDark,
  theme,
  onInfoClick,
  onEtfClick,
}: {
  holding: XRayHolding;
  rank: number;
  privacy: boolean;
  isDark: boolean;
  theme: ReturnType<typeof useMantineTheme>;
  onInfoClick: (symbol: string) => void;
  onEtfClick: (symbol: string) => void;
}) {
  return (
    <Box
      px="sm"
      py="xs"
      style={{
        borderRadius: 10,
        border: `1px solid ${isDark ? theme.colors.dark[4] : theme.colors.gray[2]}`,
        background: isDark ? theme.colors.dark[6] : theme.colors.gray[0],
      }}
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <div style={{ flex: 1, minWidth: 0 }}>
          <Group gap={6} wrap="nowrap">
            <Text size="xs" c="dimmed" fw={700}>{rank}</Text>
            <Text size="sm" fw={600} lineClamp={1}>{holding.name || holding.symbol}</Text>
            <ActionIcon
              variant="subtle"
              color="gray"
              size="xs"
              onClick={() => onInfoClick(holding.symbol)}
              aria-label={`Dettaglio ${holding.symbol}`}
            >
              <IconInfoCircle size={14} />
            </ActionIcon>
          </Group>
          <Text size="xs" c="dimmed" lineClamp={1}>{holding.symbol}</Text>
        </div>
        <Text size="sm" fw={700} style={{ flexShrink: 0 }}>
          {privacy ? PRIVACY_MASK : `${holding.aggregated_weight_pct.toFixed(2)}%`}
        </Text>
      </Group>
      {holding.etf_contributors.length > 0 && (
        <Group gap={4} mt={4} wrap="wrap">
          {holding.etf_contributors.map((etf) => (
            <EtfBadge key={etf} symbol={etf} onClick={onEtfClick} />
          ))}
        </Group>
      )}
    </Box>
  );
}

export function XRayCard({ portfolioId }: Props) {
  const { data: xray, isLoading, error } = usePortfolioXray(portfolioId);
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');
  const [expandedEtf, setExpandedEtf] = useState<string | null>(null);
  const [infoModal, setInfoModal] = useState<{ symbol: string } | null>(null);
  const privacy = isPrivacyModeEnabled();

  const openInfo = (symbol: string) => setInfoModal({ symbol });

  if (isLoading) {
    return (
      <Card withBorder radius="xl" padding="xl">
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      </Card>
    );
  }

  if (error) {
    return (
      <Card withBorder radius="xl" padding="xl">
        <Alert color="red" variant="light">
          Impossibile caricare i dati X-Ray: {error instanceof Error ? error.message : 'Errore sconosciuto'}
        </Alert>
      </Card>
    );
  }

  if (!xray || xray.etf_count === 0) {
    return (
      <Card withBorder radius="xl" padding="xl">
        <Group gap="sm" mb="md">
          <ThemeIcon color="indigo" variant="light" radius="xl">
            <IconSearch size={18} />
          </ThemeIcon>
          <Title order={4}>X-Ray: Titoli Sottostanti</Title>
        </Group>
        {xray?.coverage_issues?.length ? (
          <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={18} />}>
            L&apos;X-Ray ha rilevato strumenti candidati, ma nessuno con holdings sufficienti. {xray.coverage_issues
              .slice(0, 2)
              .map((issue) => `${issue.symbol}: ${formatXrayFailureReason(issue.reason)}`)
              .join(' • ')}
          </Alert>
        ) : (
          <Alert color="blue" variant="light">
            Nessun ETF/fondo presente nel portafoglio. L&apos;X-Ray analizza la composizione degli ETF.
          </Alert>
        )}
      </Card>
    );
  }

  return (
    <>
      <Card withBorder radius="xl" padding="lg">
        <Stack gap="md">
          <Group justify="space-between" align="center" wrap="wrap">
            <Group gap="sm">
              <ThemeIcon color="indigo" variant="light" radius="xl">
                <IconSearch size={18} />
              </ThemeIcon>
              <Title order={4}>X-Ray: Titoli Sottostanti</Title>
            </Group>
            <Group gap="xs">
              <Badge variant="light" color="indigo">
                {xray.etf_count} ETF analizzati
              </Badge>
              <Badge variant="light" color={xray.coverage_pct >= 80 ? 'teal' : 'yellow'}>
                Copertura {privacy ? PRIVACY_MASK : `${xray.coverage_pct}%`}
              </Badge>
            </Group>
          </Group>

          {xray.coverage_issues.length > 0 && (
            <Alert
              color="yellow"
              variant="light"
              icon={<IconAlertTriangle size={18} />}
              title="Copertura X-Ray parziale"
            >
              <Text size="sm">
                {xray.coverage_issues.length === 1
                  ? 'Un ETF/fondo non ha holdings affidabili disponibili.'
                  : `${xray.coverage_issues.length} ETF/fondi non hanno holdings affidabili disponibili.`}
              </Text>
              <Text size="xs" c="dimmed" mt={4}>
                {xray.coverage_issues
                  .slice(0, 3)
                  .map((issue) => `${issue.symbol}: ${formatXrayFailureReason(issue.reason)}`)
                  .join(' • ')}
              </Text>
            </Alert>
          )}

          {/* Aggregated country & sector exposure from justETF */}
          {(Object.keys(xray.aggregated_country_exposure ?? {}).length > 0 ||
            Object.keys(xray.aggregated_sector_exposure ?? {}).length > 0) && (
            <Box>
              <Group gap="xl" align="flex-start" wrap="wrap">
                {Object.keys(xray.aggregated_country_exposure ?? {}).length > 0 && (
                  <Stack gap={4} style={{ flex: 1, minWidth: 200 }}>
                    <Text size="sm" fw={600} mb={4}>Esposizione Geografica</Text>
                    {Object.entries(xray.aggregated_country_exposure).slice(0, 8).map(([country, weight]) => (
                      <Group key={country} justify="space-between" gap="xs" wrap="nowrap">
                        <Text size="xs" truncate style={{ flex: 1 }}>{country}</Text>
                        <Group gap={4} wrap="nowrap" style={{ flexShrink: 0 }}>
                          <Progress value={Math.min(weight, 100)} size="xs" color="blue" style={{ width: 50 }} />
                          <Text size="xs" fw={500} w={42} ta="right">{weight.toFixed(1)}%</Text>
                        </Group>
                      </Group>
                    ))}
                  </Stack>
                )}
                {Object.keys(xray.aggregated_sector_exposure ?? {}).length > 0 && (
                  <Stack gap={4} style={{ flex: 1, minWidth: 200 }}>
                    <Text size="sm" fw={600} mb={4}>Esposizione Settoriale</Text>
                    {Object.entries(xray.aggregated_sector_exposure).slice(0, 8).map(([sector, weight]) => (
                      <Group key={sector} justify="space-between" gap="xs" wrap="nowrap">
                        <Text size="xs" truncate style={{ flex: 1 }}>{sector}</Text>
                        <Group gap={4} wrap="nowrap" style={{ flexShrink: 0 }}>
                          <Progress value={Math.min(weight, 100)} size="xs" color="violet" style={{ width: 50 }} />
                          <Text size="xs" fw={500} w={42} ta="right">{weight.toFixed(1)}%</Text>
                        </Group>
                      </Group>
                    ))}
                  </Stack>
                )}
              </Group>
            </Box>
          )}

          {/* Aggregated holdings */}
          {xray.aggregated_holdings.length > 0 && (
            <Box>
              <Text size="sm" fw={600} mb="xs">
                Top titoli sottostanti (aggregati da tutti gli ETF)
              </Text>

              {isMobile ? (
                /* ---- Mobile: card layout ---- */
                <Stack gap="xs">
                  {xray.aggregated_holdings.map((h, i) => (
                    <HoldingCard
                      key={h.symbol}
                      holding={h}
                      rank={i + 1}
                      privacy={privacy}
                      isDark={isDark}
                      theme={theme}
                      onInfoClick={openInfo}
                      onEtfClick={openInfo}
                    />
                  ))}
                </Stack>
              ) : (
                /* ---- Desktop: table layout ---- */
                <Table withTableBorder withColumnBorders highlightOnHover style={{ tableLayout: 'fixed' }}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th style={{ width: 50 }}>#</Table.Th>
                      <Table.Th>Titolo</Table.Th>
                      <Table.Th style={{ width: 100, textAlign: 'right' }}>Peso</Table.Th>
                      <Table.Th style={{ width: 200 }}>Presente in</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {xray.aggregated_holdings.map((h, i) => (
                      <Table.Tr key={h.symbol}>
                        <Table.Td>
                          <Text size="sm" c="dimmed">{i + 1}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Group gap={4} wrap="nowrap">
                            <Text size="sm" fw={500} lineClamp={1}>{h.name || h.symbol}</Text>
                            <Tooltip label="Dettaglio asset" withArrow>
                              <ActionIcon
                                variant="subtle"
                                color="gray"
                                size="xs"
                                onClick={() => openInfo(h.symbol)}
                                aria-label={`Dettaglio ${h.symbol}`}
                              >
                                <IconInfoCircle size={14} />
                              </ActionIcon>
                            </Tooltip>
                          </Group>
                          <Text size="xs" c="dimmed">{h.symbol}</Text>
                        </Table.Td>
                        <Table.Td style={{ textAlign: 'right' }}>
                          <Text size="sm" fw={600}>
                            {privacy ? PRIVACY_MASK : `${h.aggregated_weight_pct.toFixed(2)}%`}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Group gap={4} wrap="wrap">
                            {h.etf_contributors.map((etf) => (
                              <EtfBadge key={etf} symbol={etf} onClick={openInfo} />
                            ))}
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Box>
          )}

          {/* Per-ETF breakdown */}
          {xray.etf_details.length > 0 && (
            <Box>
              <Text size="sm" fw={600} mb="xs">
                Dettaglio per ETF
              </Text>
              <Stack gap="xs">
                {xray.etf_details.map((etf) => {
                  const isExpanded = expandedEtf === etf.symbol;
                  const sourceTone = getHoldingsSourceTone(etf);
                  return (
                    <Box
                      key={etf.symbol}
                      style={{
                        borderRadius: 8,
                        border: `1px solid ${isDark ? theme.colors.dark[4] : theme.colors.gray[2]}`,
                        overflow: 'hidden',
                      }}
                    >
                      <UnstyledButton
                        onClick={() => setExpandedEtf(isExpanded ? null : etf.symbol)}
                        w="100%"
                        px="sm"
                        py="xs"
                        style={{
                          background: isDark ? theme.colors.dark[6] : theme.colors.gray[0],
                        }}
                      >
                        <Group justify="space-between" wrap={isMobile ? 'wrap' : 'nowrap'}>
                          <Group gap="sm" wrap="nowrap">
                            {isExpanded ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
                            <div>
                              <Group gap={4} wrap="nowrap">
                                <Text size="sm" fw={600} lineClamp={1}>{etf.name || etf.symbol}</Text>
                                <Tooltip label={`Dettaglio ${etf.symbol}`} withArrow>
                                  <ActionIcon
                                    variant="subtle"
                                    color="gray"
                                    size="xs"
                                    onClick={(e) => { e.stopPropagation(); openInfo(etf.symbol); }}
                                    aria-label={`Dettaglio ${etf.symbol}`}
                                  >
                                    <IconInfoCircle size={14} />
                                  </ActionIcon>
                                </Tooltip>
                              </Group>
                              <Text size="xs" c="dimmed">{etf.symbol}</Text>
                            </div>
                          </Group>
                          <Group gap="xs" wrap="wrap">
                            {etf.investment_focus && (
                              <Badge size="sm" variant="light" color="grape">
                                {etf.investment_focus}
                              </Badge>
                            )}
                            <Badge size="sm" variant="light" color="blue">
                              {privacy ? PRIVACY_MASK : `${etf.portfolio_weight_pct.toFixed(1)}%`} del portafoglio
                            </Badge>
                            <Badge size="sm" variant="light" color={sourceTone.color}>
                              {sourceTone.label}
                            </Badge>
                            {!etf.holdings_available && (
                              <Badge size="sm" variant="light" color="orange">
                                Dati non disponibili
                              </Badge>
                            )}
                          </Group>
                        </Group>
                      </UnstyledButton>
                      <Collapse in={isExpanded}>
                        {etf.holdings_available && etf.top_holdings.length > 0 ? (
                          <Box px="sm" py="xs">
                            <Stack gap={4}>
                              {etf.top_holdings.map((h) => (
                                <Group key={h.symbol} justify="space-between" wrap="nowrap">
                                  <Group gap="xs" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                                    <Text size="xs" fw={500} style={{ flexShrink: 0 }}>{h.symbol}</Text>
                                    <Text size="xs" c="dimmed" lineClamp={1}>{h.name}</Text>
                                    <ActionIcon
                                      variant="subtle"
                                      color="gray"
                                      size="xs"
                                      onClick={() => openInfo(h.symbol)}
                                      aria-label={`Dettaglio ${h.symbol}`}
                                      style={{ flexShrink: 0 }}
                                    >
                                      <IconInfoCircle size={12} />
                                    </ActionIcon>
                                  </Group>
                                  <Group gap="xs" wrap="nowrap" style={{ flexShrink: 0 }}>
                                    <Progress
                                      value={Math.min(h.aggregated_weight_pct, 100)}
                                      size="sm"
                                      color="indigo"
                                      w={60}
                                    />
                                    <Text size="xs" fw={600} w={50} ta="right">
                                      {privacy ? PRIVACY_MASK : `${h.aggregated_weight_pct.toFixed(1)}%`}
                                    </Text>
                                  </Group>
                                </Group>
                              ))}
                            </Stack>
                          </Box>
                        ) : (
                          <Box px="sm" py="xs">
                            <Text size="xs" c="dimmed">
                              {formatXrayFailureReason(etf.failure_reason) ?? 'Dati sulle posizioni sottostanti non disponibili per questo ETF.'}
                            </Text>
                          </Box>
                        )}
                      </Collapse>
                    </Box>
                  );
                })}
              </Stack>
            </Box>
          )}
        </Stack>
      </Card>

      {/* Asset Info Modal */}
      <AssetInfoModal
        symbol={infoModal?.symbol ?? ''}
        opened={infoModal != null}
        onClose={() => setInfoModal(null)}
      />
    </>
  );
}
