import { useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Card,
  Collapse,
  Group,
  Loader,
  Progress,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
  UnstyledButton,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import { IconChevronDown, IconChevronUp, IconFlame } from '@tabler/icons-react';
import { useStressTest } from '../dashboard/hooks/queries';
import type { StressTestScenarioResult } from '../../services/api';

interface Props {
  portfolioId: number | null;
}

function riskColor(level: string): string {
  switch (level) {
    case 'low': return 'teal';
    case 'medium': return 'yellow';
    case 'high': return 'orange';
    case 'critical': return 'red';
    default: return 'gray';
  }
}

function riskLabel(level: string): string {
  switch (level) {
    case 'low': return 'Basso';
    case 'medium': return 'Medio';
    case 'high': return 'Alto';
    case 'critical': return 'Critico';
    default: return level;
  }
}

function formatImpact(pct: number | null | undefined): string {
  if (pct == null || !Number.isFinite(pct)) return 'N/D';
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}

function ScenarioCard({ scenario, isDark }: { scenario: StressTestScenarioResult; isDark: boolean }) {
  const theme = useMantineTheme();
  const [expanded, setExpanded] = useState(false);
  const impactAbs = Math.abs(scenario.estimated_portfolio_impact_pct);

  return (
    <Box
      style={{
        borderRadius: 16,
        padding: '16px 18px',
        background: isDark
          ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
          : 'linear-gradient(180deg, #f8fafc 0%, #ffffff 100%)',
        border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e2e8f0',
      }}
    >
      <Group justify="space-between" align="flex-start" wrap="wrap" gap="xs">
        <div style={{ minWidth: 0, flex: 1 }}>
          <Group gap="xs" wrap="wrap">
            <Text fw={700} size="sm">{scenario.scenario_name}</Text>
            <Badge size="xs" variant="light" color={scenario.scenario_type === 'historical' ? 'blue' : 'grape'}>
              {scenario.scenario_type === 'historical' ? 'Storico' : 'Shock'}
            </Badge>
          </Group>
          {scenario.period && (
            <Text size="xs" c="dimmed">{scenario.period}</Text>
          )}
        </div>
        <Badge size="lg" color={riskColor(scenario.risk_level)} variant="filled">
          {formatImpact(scenario.estimated_portfolio_impact_pct)}
        </Badge>
      </Group>

      <Progress.Root size="sm" mt="sm" radius="xl">
        <Progress.Section
          value={Math.min(impactAbs, 100)}
          color={riskColor(scenario.risk_level)}
        />
      </Progress.Root>

      <Group mt="xs" gap="lg" wrap="wrap">
        <div>
          <Text size="xs" c="dimmed">Rischio</Text>
          <Badge size="sm" variant="light" color={riskColor(scenario.risk_level)}>
            {riskLabel(scenario.risk_level)}
          </Badge>
        </div>
        {scenario.max_drawdown_pct != null && (
          <div>
            <Text size="xs" c="dimmed">Max Drawdown</Text>
            <Text size="sm" fw={600}>{formatImpact(scenario.max_drawdown_pct)}</Text>
          </div>
        )}
        {scenario.recovery_months != null && (
          <div>
            <Text size="xs" c="dimmed">Recovery</Text>
            <Text size="sm" fw={600}>{scenario.recovery_months} mesi</Text>
          </div>
        )}
        {scenario.benchmark_drawdown_pct != null && (
          <div>
            <Text size="xs" c="dimmed">Benchmark</Text>
            <Text size="sm" fw={600}>{formatImpact(scenario.benchmark_drawdown_pct)}</Text>
          </div>
        )}
      </Group>

      {scenario.most_impacted_assets.length > 0 && (
        <>
          <UnstyledButton onClick={() => setExpanded((v) => !v)} mt="xs">
            <Group gap={4}>
              <Text size="xs" c="dimmed" fw={600}>Asset piu colpiti</Text>
              {expanded ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
            </Group>
          </UnstyledButton>
          <Collapse in={expanded}>
            <Table size="xs" mt="xs" withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Asset</Table.Th>
                  <Table.Th>Peso</Table.Th>
                  <Table.Th>Impatto</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {scenario.most_impacted_assets.map((asset) => (
                  <Table.Tr key={asset.symbol}>
                    <Table.Td>
                      <Text size="xs" fw={500} style={{ wordBreak: 'break-word' }}>{asset.name}</Text>
                      <Text size="xs" c="dimmed">{asset.symbol}</Text>
                    </Table.Td>
                    <Table.Td><Text size="xs">{asset.weight_pct.toFixed(1)}%</Text></Table.Td>
                    <Table.Td>
                      <Text size="xs" fw={600} c={asset.estimated_loss_pct < 0 ? 'red' : 'teal'}>
                        {formatImpact(asset.estimated_loss_pct)}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Collapse>
        </>
      )}
    </Box>
  );
}

export function StressTestCard({ portfolioId }: Props) {
  const { data, isLoading, error } = useStressTest(portfolioId);
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const [filter, setFilter] = useState<string>('all');

  if (isLoading && portfolioId != null) {
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
      <Card withBorder radius="xl" padding="lg">
        <Alert color="red">Errore nel caricamento dello stress test.</Alert>
      </Card>
    );
  }

  if (!data || data.scenarios.length === 0) {
    return (
      <Card withBorder radius="xl" padding="lg">
        <Group gap="sm" mb="md">
          <ThemeIcon color="red" variant="light" radius="xl">
            <IconFlame size={18} />
          </ThemeIcon>
          <Title order={4}>Stress Test</Title>
        </Group>
        <Alert color="yellow" variant="light">
          Dati insufficienti per eseguire lo stress test del portafoglio.
        </Alert>
      </Card>
    );
  }

  const filteredScenarios = data.scenarios.filter((s) => {
    if (filter === 'historical') return s.scenario_type === 'historical';
    if (filter === 'shock') return s.scenario_type === 'shock';
    return true;
  });

  const worstScenario = data.scenarios.reduce((worst, s) =>
    s.estimated_portfolio_impact_pct < worst.estimated_portfolio_impact_pct ? s : worst
  , data.scenarios[0]);

  return (
    <Card withBorder radius="xl" padding="lg">
      <Stack gap="md">
        <Group gap="sm" justify="space-between" wrap="wrap">
          <Group gap="sm">
            <ThemeIcon color="red" variant="light" radius="xl">
              <IconFlame size={18} />
            </ThemeIcon>
            <div style={{ minWidth: 0 }}>
              <Title order={4}>Stress Test</Title>
              <Text size="xs" c="dimmed">
                {data.scenarios.length} scenari
                {data.portfolio_volatility_pct != null && <> &middot; vol. {data.portfolio_volatility_pct.toFixed(1)}%</>}
                {' '}&middot; worst case: {formatImpact(worstScenario.estimated_portfolio_impact_pct)}
              </Text>
            </div>
          </Group>
          <SegmentedControl
            size="xs"
            value={filter}
            onChange={setFilter}
            data={[
              { label: 'Tutti', value: 'all' },
              { label: 'Storici', value: 'historical' },
              { label: 'Shock', value: 'shock' },
            ]}
          />
        </Group>

        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          {filteredScenarios.map((scenario) => (
            <ScenarioCard key={scenario.scenario_id} scenario={scenario} isDark={isDark} />
          ))}
        </SimpleGrid>

        <Text size="xs" c="dimmed" fs="italic">
          Gli stress test si basano su dati storici e scenari ipotetici. Non costituiscono previsioni di perdite future.
        </Text>
      </Stack>
    </Card>
  );
}
