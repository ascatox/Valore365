import { useEffect, useState, useMemo } from 'react';
import { ActionIcon, Badge, Button, Divider, Grid, Group, Loader, Modal, Paper, Progress, Stack, Table, Text, Tooltip } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import { IconInfoCircle, IconRefresh } from '@tabler/icons-react';
import type { AssetInfo, EtfEnrichment } from '../../../services/api';
import { getAssetInfo, getMarketSymbolInfo, getEtfEnrichment, refreshEtfEnrichment } from '../../../services/api';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../formatters';

function formatMarketCap(value: number | null): string {
  if (value == null) return 'N/D';
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  return formatNum(value, 0);
}

function formatVolume(value: number | null): string {
  if (value == null) return 'N/D';
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return formatNum(value, 0);
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <Group justify="space-between" gap="xs">
      <Text size="sm" c="dimmed">{label}</Text>
      <Text size="sm" fw={500}>{value}</Text>
    </Group>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <Text size="xs" fw={700} tt="uppercase" c="dimmed" mt={4}>{children}</Text>;
}

function WeightBar({ items, colorMap }: { items: { name: string; percentage: number }[]; colorMap: string[] }) {
  const top = items.slice(0, 8);
  const otherPct = items.slice(8).reduce((s, i) => s + i.percentage, 0);
  return (
    <Stack gap={4}>
      {top.map((item, i) => (
        <Group key={item.name} justify="space-between" gap="xs" wrap="nowrap">
          <Group gap={6} wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
            <div style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: colorMap[i % colorMap.length], flexShrink: 0 }} />
            <Text size="xs" truncate style={{ flex: 1 }}>{item.name}</Text>
          </Group>
          <Group gap={4} wrap="nowrap" style={{ flexShrink: 0 }}>
            <Progress value={item.percentage} size="xs" color={colorMap[i % colorMap.length]} style={{ width: 50 }} />
            <Text size="xs" fw={500} w={42} ta="right">{formatNum(item.percentage, 1)}%</Text>
          </Group>
        </Group>
      ))}
      {otherPct > 0.1 && (
        <Group justify="space-between" gap="xs">
          <Text size="xs" c="dimmed">Altro</Text>
          <Text size="xs" fw={500}>{formatNum(otherPct, 1)}%</Text>
        </Group>
      )}
    </Stack>
  );
}

const COUNTRY_COLORS = ['#228be6', '#40c057', '#fab005', '#fa5252', '#be4bdb', '#15aabf', '#fd7e14', '#74c0fc'];
const SECTOR_COLORS = ['#7048e8', '#12b886', '#e8590c', '#4263eb', '#f06595', '#20c997', '#845ef7', '#fcc419'];

function PriceHistoryChart({ data, currency }: { data: { date: string; close: number }[]; currency: string | null }) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const gridColor = isDark ? theme.colors.dark[4] : '#e9ecef';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  const chartData = useMemo(() =>
    data.map((p) => ({
      date: new Date(p.date).toLocaleDateString('it-IT', { month: '2-digit', year: '2-digit' }),
      close: p.close,
      rawDate: p.date,
    })),
    [data],
  );

  const first = data[0]?.close ?? 0;
  const last = data[data.length - 1]?.close ?? 0;
  const changePct = first > 0 ? ((last / first) - 1) * 100 : 0;
  const color = changePct >= 0 ? '#16a34a' : '#dc2626';

  return (
    <Stack gap={4}>
      <Group justify="space-between" gap="xs">
        <Text size="xs" fw={600}>Storico 5 anni</Text>
        <Text size="xs" fw={600} c={changePct >= 0 ? 'green' : 'red'}>
          {changePct >= 0 ? '+' : ''}{formatNum(changePct, 1)}%
        </Text>
      </Group>
      <div style={{ height: 140 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="assetInfoGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.15} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
            <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: tickColor, fontSize: 10 }} interval="preserveStartEnd" />
            <YAxis hide domain={['auto', 'auto']} />
            <RechartsTooltip
              content={({ active, payload, label }: any) => {
                if (!active || !payload?.length) return null;
                const val = Number(payload[0]?.value ?? 0);
                return (
                  <Paper withBorder p="xs" radius="sm" shadow="xs">
                    <Text size="xs" c="dimmed">{label}</Text>
                    <Text size="sm" fw={600}>{formatMoney(val, currency ?? 'USD')}</Text>
                  </Paper>
                );
              }}
            />
            <Area type="monotone" dataKey="close" stroke={color} strokeWidth={1.5} fillOpacity={1} fill="url(#assetInfoGrad)" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Stack>
  );
}

interface AssetInfoModalProps {
  assetId?: number;
  symbol: string;
  opened: boolean;
  onClose: () => void;
}

export function AssetInfoModal({ assetId, symbol, opened, onClose }: AssetInfoModalProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');
  const [info, setInfo] = useState<AssetInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ETF enrichment state
  const [enrichment, setEnrichment] = useState<EtfEnrichment | null>(null);
  const [enrichLoading, setEnrichLoading] = useState(false);
  const [enrichRefreshing, setEnrichRefreshing] = useState(false);

  useEffect(() => {
    if (!opened) return;
    let active = true;
    setLoading(true);
    setError(null);
    setInfo(null);
    setEnrichment(null);
    const fetcher = assetId != null ? getAssetInfo(assetId) : getMarketSymbolInfo(symbol);
    fetcher
      .then((data) => { if (active) setInfo(data); })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : 'Errore nel caricamento'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [opened, assetId, symbol]);

  // Fetch enrichment data when we have an ETF with asset_id
  useEffect(() => {
    if (!info) return;
    const isFund = info.asset_type === 'etf' || info.asset_type === 'fund';
    if (!isFund || info.asset_id == null) return;
    let active = true;
    setEnrichLoading(true);
    getEtfEnrichment(info.asset_id)
      .then((data) => { if (active) setEnrichment(data); })
      .catch(() => {})
      .finally(() => { if (active) setEnrichLoading(false); });
    return () => { active = false; };
  }, [info]);

  const handleRefreshEnrichment = () => {
    if (!info?.asset_id || enrichRefreshing) return;
    setEnrichRefreshing(true);
    refreshEtfEnrichment(info.asset_id)
      .then((data) => setEnrichment(data))
      .catch(() => {})
      .finally(() => setEnrichRefreshing(false));
  };

  const isFundLike = info?.asset_type === 'etf' || info?.asset_type === 'fund';
  const hasEnrichment = enrichment != null;

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Group gap="xs">
          <IconInfoCircle size={20} />
          <div>
            <Text fw={600}>{info?.name ?? symbol}</Text>
            {info?.name && <Text size="xs" c="dimmed">{symbol}</Text>}
          </div>
        </Group>
      }
      size={isMobile ? '100%' : 'lg'}
      fullScreen={isMobile}
      centered={!isMobile}
    >
      {loading && (
        <Group justify="center" py="xl">
          <Loader size="sm" />
          <Text c="dimmed" size="sm">Caricamento informazioni...</Text>
        </Group>
      )}
      {error && (
        <Text c="red" size="sm" ta="center" py="xl">{error}</Text>
      )}
      {info && !loading && (
        <Stack gap="md">
          <Group gap="xs">
            {info.asset_type && (
              <Badge variant="light" color="blue" size="md">
                {info.asset_type.toUpperCase()}
              </Badge>
            )}
            {info.quote_type && info.quote_type.toUpperCase() !== info.asset_type?.toUpperCase() && (
              <Badge variant="outline" color="gray" size="sm">
                {info.quote_type}
              </Badge>
            )}
            {info.category && (
              <Badge variant="outline" color="teal" size="sm">
                {info.category}
              </Badge>
            )}
            {enrichment?.replication_method && (
              <Badge variant="outline" color="violet" size="sm">
                {enrichment.replication_method}
              </Badge>
            )}
            {enrichment?.distribution_policy && (
              <Badge variant="outline" color="orange" size="sm">
                {enrichment.distribution_policy}
              </Badge>
            )}
          </Group>

          {info.current_price != null && (
            <Group gap="sm" align="center">
              <Text fw={700} size="lg">{formatMoney(info.current_price, info.currency ?? 'USD')}</Text>
              {info.day_change_pct != null && (
                <Badge
                  variant="light"
                  color={getVariationColor(info.day_change_pct)}
                  size="lg"
                  styles={{ root: { fontSize: 14, fontWeight: 600 } }}
                >
                  {formatPct(info.day_change_pct)}
                </Badge>
              )}
            </Group>
          )}

          {/* --- Costi & Fondo (ETF/Fund) --- */}
          {isFundLike && (info.expense_ratio != null || info.fund_family || info.total_assets != null || hasEnrichment) && (
            <>
              <Divider />
              <Group justify="space-between" align="center">
                <SectionTitle>Costi e Fondo</SectionTitle>
                {isFundLike && info.asset_id != null && (
                  <Tooltip label={hasEnrichment ? 'Aggiorna dati justETF' : 'Carica dati da justETF'}>
                    <ActionIcon
                      variant="subtle"
                      size="xs"
                      loading={enrichRefreshing || enrichLoading}
                      onClick={handleRefreshEnrichment}
                    >
                      <IconRefresh size={14} />
                    </ActionIcon>
                  </Tooltip>
                )}
              </Group>
              <Grid gutter="md">
                <Grid.Col span={6}>
                  <Stack gap={6}>
                    {(enrichment?.ter != null || info.expense_ratio != null) && (
                      <InfoRow
                        label="TER"
                        value={enrichment?.ter != null
                          ? formatPct(enrichment.ter * 100)
                          : formatPct(info.expense_ratio! * 100)
                        }
                      />
                    )}
                    {(enrichment?.fund_provider || info.fund_family) && (
                      <InfoRow label="Emittente" value={enrichment?.fund_provider || info.fund_family!} />
                    )}
                    {enrichment?.domicile && <InfoRow label="Domicilio" value={enrichment.domicile} />}
                    {enrichment?.inception_date && <InfoRow label="Lancio" value={enrichment.inception_date} />}
                  </Stack>
                </Grid.Col>
                <Grid.Col span={6}>
                  <Stack gap={6}>
                    {(enrichment?.fund_size_eur != null || info.total_assets != null) && (
                      <InfoRow
                        label="AUM"
                        value={enrichment?.fund_size_eur != null
                          ? formatMarketCap(enrichment.fund_size_eur)
                          : formatMarketCap(info.total_assets)
                        }
                      />
                    )}
                    {info.dividend_yield != null && (
                      <InfoRow label="Dist. Yield" value={formatPct(info.dividend_yield * 100)} />
                    )}
                    {enrichment?.fund_currency && <InfoRow label="Valuta fondo" value={enrichment.fund_currency} />}
                    {enrichment?.volatility_1y != null && (
                      <InfoRow label="Volatilità 1Y" value={formatPct(enrichment.volatility_1y * 100)} />
                    )}
                    {enrichment?.currency_hedged != null && (
                      <InfoRow label="Hedging valuta" value={enrichment.currency_hedged ? 'Sì' : 'No'} />
                    )}
                  </Stack>
                </Grid.Col>
              </Grid>
              {enrichment?.index_tracked && (
                <InfoRow label="Indice replicato" value={enrichment.index_tracked} />
              )}
            </>
          )}

          {/* --- Esposizione Geografica (justETF) --- */}
          {hasEnrichment && enrichment.country_weights && enrichment.country_weights.length > 0 && (
            <>
              <Divider />
              <SectionTitle>Esposizione Geografica</SectionTitle>
              <WeightBar items={enrichment.country_weights} colorMap={COUNTRY_COLORS} />
            </>
          )}

          {/* --- Settori (justETF) --- */}
          {hasEnrichment && enrichment.sector_weights && enrichment.sector_weights.length > 0 && (
            <>
              <Divider />
              <SectionTitle>Settori</SectionTitle>
              <WeightBar items={enrichment.sector_weights} colorMap={SECTOR_COLORS} />
            </>
          )}

          {/* --- Top Holdings (justETF) --- */}
          {hasEnrichment && enrichment.top_holdings && enrichment.top_holdings.length > 0 && (
            <>
              <Divider />
              <Group justify="space-between" align="center">
                <SectionTitle>Top Holdings</SectionTitle>
                {enrichment.holdings_date && (
                  <Text size="xs" c="dimmed">{enrichment.holdings_date}</Text>
                )}
              </Group>
              <Table striped highlightOnHover withTableBorder size="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Nome</Table.Th>
                    <Table.Th ta="right">Peso</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {enrichment.top_holdings.slice(0, 10).map((h, i) => (
                    <Table.Tr key={i}>
                      <Table.Td>
                        <Text size="xs" truncate>{h.name ?? 'N/D'}</Text>
                        {h.isin && <Text size="xs" c="dimmed">{h.isin}</Text>}
                      </Table.Td>
                      <Table.Td ta="right">
                        <Text size="xs" fw={500}>
                          {h.percentage != null ? `${formatNum(h.percentage, 2)}%` : 'N/D'}
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </>
          )}

          {/* --- Enrichment CTA when no data yet --- */}
          {isFundLike && !hasEnrichment && !enrichLoading && info.asset_id != null && (
            <>
              <Divider />
              <Button
                variant="light"
                size="xs"
                leftSection={<IconRefresh size={14} />}
                loading={enrichRefreshing}
                onClick={handleRefreshEnrichment}
              >
                Carica dettagli ETF da justETF
              </Button>
            </>
          )}

          {/* --- Fondamentali (Stock) --- */}
          <Divider />
          <SectionTitle>Fondamentali</SectionTitle>
          <Grid gutter="md">
            <Grid.Col span={6}>
              <Stack gap={6}>
                {info.sector && <InfoRow label="Settore" value={info.sector} />}
                {info.industry && <InfoRow label="Industria" value={info.industry} />}
                {info.country && <InfoRow label="Paese" value={info.country} />}
                {info.currency && <InfoRow label="Valuta" value={info.currency} />}
              </Stack>
            </Grid.Col>
            <Grid.Col span={6}>
              <Stack gap={6}>
                <InfoRow label="Market Cap" value={formatMarketCap(info.market_cap)} />
                {info.trailing_pe != null && <InfoRow label="P/E (TTM)" value={formatNum(info.trailing_pe)} />}
                {info.forward_pe != null && <InfoRow label="P/E (Fwd)" value={formatNum(info.forward_pe)} />}
                {!isFundLike && info.dividend_yield != null && (
                  <InfoRow label="Div. Yield" value={formatPct(info.dividend_yield * 100)} />
                )}
                {info.beta != null && <InfoRow label="Beta" value={formatNum(info.beta)} />}
                <InfoRow label="Vol. Medio" value={formatVolume(info.avg_volume)} />
              </Stack>
            </Grid.Col>
          </Grid>

          {/* --- Range & Redditività --- */}
          {(info.fifty_two_week_high != null || info.profit_margins != null || info.return_on_equity != null) && (
            <>
              <Divider />
              <SectionTitle>Range e Margini</SectionTitle>
              <Grid gutter="md">
                <Grid.Col span={6}>
                  <Stack gap={6}>
                    {info.fifty_two_week_low != null && info.fifty_two_week_high != null && (
                      <InfoRow
                        label="52 sett."
                        value={`${formatMoney(info.fifty_two_week_low, info.currency ?? 'USD')} – ${formatMoney(info.fifty_two_week_high, info.currency ?? 'USD')}`}
                      />
                    )}
                    {info.revenue_growth != null && (
                      <InfoRow label="Crescita ricavi" value={formatPct(info.revenue_growth * 100)} />
                    )}
                    {info.earnings_growth != null && (
                      <InfoRow label="Crescita utili" value={formatPct(info.earnings_growth * 100)} />
                    )}
                  </Stack>
                </Grid.Col>
                <Grid.Col span={6}>
                  <Stack gap={6}>
                    {info.profit_margins != null && (
                      <InfoRow label="Margine netto" value={formatPct(info.profit_margins * 100)} />
                    )}
                    {info.return_on_equity != null && (
                      <InfoRow label="ROE" value={formatPct(info.return_on_equity * 100)} />
                    )}
                  </Stack>
                </Grid.Col>
              </Grid>
            </>
          )}

          {info.price_history_5y.length > 0 && (
            <PriceHistoryChart data={info.price_history_5y} currency={info.currency} />
          )}

          {(enrichment?.description || info.description) && (
            <Text size="xs" c="dimmed" lineClamp={6} style={{ lineHeight: 1.5 }}>
              {enrichment?.description || info.description}
            </Text>
          )}

          {info.website && (
            <Text size="xs" c="blue" component="a" href={info.website} target="_blank" rel="noopener noreferrer">
              {info.website}
            </Text>
          )}

          {hasEnrichment && enrichment.fetched_at && (
            <Text size="xs" c="dimmed" ta="right">
              justETF aggiornato: {new Date(enrichment.fetched_at).toLocaleDateString('it-IT')}
            </Text>
          )}
        </Stack>
      )}
    </Modal>
  );
}
