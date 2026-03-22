import { useMemo, useState, type CSSProperties } from 'react';
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Divider,
  Drawer,
  Group,
  Paper,
  Popover,
  ScrollArea,
  Stack,
  Text,
  TextInput,
  UnstyledButton,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import {
  IconBriefcase2,
  IconCheck,
  IconChevronDown,
  IconCopy,
  IconEdit,
  IconExternalLink,
  IconPlus,
  IconSearch,
  IconTarget,
  IconTrash,
  IconWallet,
} from '@tabler/icons-react';
import type { Portfolio } from '../../services/api';

interface PortfolioSwitcherProps {
  portfolios: Portfolio[];
  value: string | null;
  onChange: (value: string) => void;
  selectedPortfolioCashBalance?: number | null;
  loading?: boolean;
  label?: string;
  emptyLabel?: string;
  style?: CSSProperties;
  onCreatePortfolio?: (() => void) | null;
  onOpenPortfolio?: (() => void) | null;
  onEditPortfolio?: (() => void) | null;
  onClonePortfolio?: (() => void) | null;
  onDeletePortfolio?: (() => void) | null;
}

const formatMoney = (value: number, currency: string) => new Intl.NumberFormat('it-IT', {
  style: 'currency',
  currency,
  maximumFractionDigits: 0,
}).format(value);

const formatDate = (value: string) => {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString('it-IT', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
};

export function PortfolioSwitcher({
  portfolios,
  value,
  onChange,
  selectedPortfolioCashBalance = null,
  loading = false,
  label,
  emptyLabel = 'Nessun portafoglio disponibile',
  style,
  onCreatePortfolio = null,
  onOpenPortfolio = null,
  onEditPortfolio = null,
  onClonePortfolio = null,
  onDeletePortfolio = null,
}: PortfolioSwitcherProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');
  const [opened, setOpened] = useState(false);
  const [query, setQuery] = useState('');

  const selectedPortfolio = useMemo(
    () => portfolios.find((portfolio) => String(portfolio.id) === value) ?? null,
    [portfolios, value],
  );

  const filteredPortfolios = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return portfolios;
    return portfolios.filter((portfolio) => (
      portfolio.name.toLowerCase().includes(normalized)
      || portfolio.base_currency.toLowerCase().includes(normalized)
      || String(portfolio.id).includes(normalized)
    ));
  }, [portfolios, query]);

  const orderedPortfolios = useMemo(() => {
    if (!value) return filteredPortfolios;
    return [...filteredPortfolios].sort((left, right) => {
      if (String(left.id) === value) return -1;
      if (String(right.id) === value) return 1;
      return left.name.localeCompare(right.name, 'it');
    });
  }, [filteredPortfolios, value]);

  const inactivePortfolios = useMemo(
    () => orderedPortfolios.filter((portfolio) => String(portfolio.id) !== value),
    [orderedPortfolios, value],
  );

  const triggerLabel = loading
    ? 'Caricamento portafogli...'
    : (selectedPortfolio?.name ?? (portfolios.length ? 'Seleziona portafoglio' : emptyLabel));

  const triggerMeta = selectedPortfolio
    ? `${selectedPortfolio.base_currency} · Cash ${formatMoney(selectedPortfolioCashBalance ?? selectedPortfolio.current_cash_balance ?? selectedPortfolio.cash_balance ?? 0, selectedPortfolio.base_currency)}`
    : (portfolios.length ? `${portfolios.length} portafogli disponibili` : emptyLabel);

  const quickActions = [
    { label: 'Apri portfolio', icon: IconExternalLink, onClick: onOpenPortfolio },
    { label: 'Modifica', icon: IconEdit, onClick: onEditPortfolio },
    { label: 'Clona', icon: IconCopy, onClick: onClonePortfolio },
    { label: 'Elimina', icon: IconTrash, onClick: onDeletePortfolio, color: 'red' },
  ].filter((action) => action.onClick);

  const list = (
    <Stack gap="sm">
      <TextInput
        value={query}
        onChange={(event) => setQuery(event.currentTarget.value)}
        placeholder="Cerca portafoglio"
        leftSection={<IconSearch size={16} />}
      />

      <ScrollArea.Autosize mah={isMobile ? '60vh' : 360} offsetScrollbars>
        <Stack gap="xs">
          {selectedPortfolio && orderedPortfolios.length > 0 && (
            <Box>
              <Text size="xs" fw={700} tt="uppercase" c={isDark ? theme.colors.gray[4] : '#64748b'} mb={8} style={{ letterSpacing: 0.8 }}>
                Attivo
              </Text>
              <UnstyledButton
                onClick={() => {
                  onChange(String(selectedPortfolio.id));
                  setOpened(false);
                  setQuery('');
                }}
                style={{
                  width: '100%',
                  borderRadius: 18,
                  border: `1px solid ${isDark ? theme.colors.teal[8] : '#0f766e'}`,
                  background: isDark ? 'rgba(20,184,166,0.12)' : 'linear-gradient(135deg, rgba(15,118,110,0.13), rgba(15,118,110,0.05))',
                  padding: '16px',
                  textAlign: 'left',
                  boxShadow: isDark ? '0 12px 28px rgba(0, 0, 0, 0.24)' : '0 12px 28px rgba(15, 118, 110, 0.10)',
                }}
              >
                <Group justify="space-between" align="flex-start" wrap="nowrap">
                  <Box style={{ minWidth: 0 }}>
                    <Group gap={8} mb={8} wrap="wrap">
                      <Text fw={700} size="sm" c={isDark ? theme.white : '#0f172a'}>{selectedPortfolio.name}</Text>
                      <Badge variant="light" color="teal" radius="xl">{selectedPortfolio.base_currency}</Badge>
                      <Badge variant="outline" color="gray" radius="xl">{`#${selectedPortfolio.id}`}</Badge>
                    </Group>
                    <Group gap={8} wrap="wrap" mb={8}>
                      <Badge variant="light" color="blue" leftSection={<IconWallet size={12} />}>
                        {`Cash ${formatMoney(selectedPortfolioCashBalance ?? selectedPortfolio.current_cash_balance ?? selectedPortfolio.cash_balance ?? 0, selectedPortfolio.base_currency)}`}
                      </Badge>
                      {selectedPortfolio.target_notional != null && (
                        <Badge variant="light" color="orange" leftSection={<IconTarget size={12} />}>
                          {`Target ${formatMoney(selectedPortfolio.target_notional, selectedPortfolio.base_currency)}`}
                        </Badge>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">
                      {`Creato ${formatDate(selectedPortfolio.created_at)} · TZ ${selectedPortfolio.timezone}`}
                    </Text>
                  </Box>
                  <IconCheck size={18} color={isDark ? theme.colors.teal[3] : '#0f766e'} style={{ flexShrink: 0, marginTop: 2 }} />
                </Group>
              </UnstyledButton>
            </Box>
          )}

          {(selectedPortfolio ? inactivePortfolios : orderedPortfolios).length ? (
            <>
              <Box>
                <Text size="xs" fw={700} tt="uppercase" c={isDark ? theme.colors.gray[4] : '#64748b'} mb={8} style={{ letterSpacing: 0.8 }}>
                  {selectedPortfolio ? 'Tutti i portafogli' : 'Portafogli'}
                </Text>
                <Stack gap="xs">
                  {(selectedPortfolio ? inactivePortfolios : orderedPortfolios).map((portfolio) => {
            const isActive = String(portfolio.id) === value;
            return (
              <UnstyledButton
                key={portfolio.id}
                onClick={() => {
                  onChange(String(portfolio.id));
                  setOpened(false);
                  setQuery('');
                }}
                style={{
                  width: '100%',
                  borderRadius: 16,
                  border: isActive
                    ? `1px solid ${isDark ? theme.colors.teal[8] : '#0f766e'}`
                    : `1px solid ${isDark ? theme.colors.dark[4] : '#d6d9de'}`,
                  background: isActive
                    ? (isDark ? 'rgba(20,184,166,0.10)' : 'linear-gradient(135deg, rgba(15,118,110,0.12), rgba(15,118,110,0.04))')
                    : (isDark ? theme.colors.dark[6] : '#ffffff'),
                  padding: '14px 16px',
                  textAlign: 'left',
                  transition: 'transform 140ms ease, border-color 140ms ease, box-shadow 140ms ease',
                  boxShadow: isActive
                    ? (isDark ? '0 12px 28px rgba(0, 0, 0, 0.24)' : '0 12px 28px rgba(15, 118, 110, 0.10)')
                    : (isDark ? '0 8px 20px rgba(0, 0, 0, 0.18)' : '0 8px 20px rgba(15, 23, 42, 0.05)'),
                }}
              >
                <Group justify="space-between" align="flex-start" wrap="nowrap">
                  <Box style={{ minWidth: 0 }}>
                    <Group gap={8} mb={6} wrap="wrap">
                      <Text fw={700} size="sm" c={isDark ? theme.white : '#0f172a'} lineClamp={1}>{portfolio.name}</Text>
                      <Badge variant="light" color="teal" radius="xl">{portfolio.base_currency}</Badge>
                      <Badge variant="outline" color="gray" radius="xl">{`#${portfolio.id}`}</Badge>
                    </Group>
                    <Group gap={8} wrap="wrap" mb={6}>
                      <Badge variant="light" color="blue" leftSection={<IconWallet size={12} />}>
                        {formatMoney(portfolio.current_cash_balance ?? portfolio.cash_balance ?? 0, portfolio.base_currency)}
                      </Badge>
                      {portfolio.target_notional != null && (
                        <Badge variant="light" color="orange" leftSection={<IconTarget size={12} />}>
                          {formatMoney(portfolio.target_notional, portfolio.base_currency)}
                        </Badge>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">
                      {`Creato ${formatDate(portfolio.created_at)} · TZ ${portfolio.timezone}`}
                    </Text>
                  </Box>
                  {isActive && <IconCheck size={18} color={isDark ? theme.colors.teal[3] : '#0f766e'} style={{ flexShrink: 0, marginTop: 2 }} />}
                </Group>
              </UnstyledButton>
            );
                  })}
                </Stack>
              </Box>
            </>
          ) : (
            <Paper radius="lg" p="md" withBorder bg={isDark ? theme.colors.dark[6] : '#f8fafc'}>
              <Text size="sm" c="dimmed">Nessun portafoglio trovato</Text>
            </Paper>
          )}
        </Stack>
      </ScrollArea.Autosize>

      {quickActions.length > 0 && selectedPortfolio && (
        <>
          <Divider />
          <Box>
            <Text size="xs" fw={700} tt="uppercase" c={isDark ? theme.colors.gray[4] : '#64748b'} mb={8} style={{ letterSpacing: 0.8 }}>
              Azioni rapide
            </Text>
            <Group gap="xs" wrap="wrap">
              {quickActions.map((action) => {
                const Icon = action.icon;
                return (
                  <Button
                    key={action.label}
                    variant="light"
                    color={action.color}
                    leftSection={<Icon size={16} />}
                    onClick={() => {
                      setOpened(false);
                      setQuery('');
                      action.onClick?.();
                    }}
                  >
                    {action.label}
                  </Button>
                );
              })}
            </Group>
          </Box>
        </>
      )}

      {onCreatePortfolio && (
        <>
          <Divider />
          <Button
            variant="light"
            leftSection={<IconPlus size={16} />}
            onClick={() => {
              setOpened(false);
              setQuery('');
              onCreatePortfolio();
            }}
          >
            Nuovo portfolio
          </Button>
        </>
      )}
    </Stack>
  );

  const trigger = (
    <UnstyledButton
      onClick={() => setOpened(true)}
      disabled={loading || portfolios.length === 0}
      style={{
        width: '100%',
        borderRadius: 18,
        border: `1px solid ${isDark ? theme.colors.dark[4] : '#d6d9de'}`,
        background: isDark
          ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
          : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
        padding: isMobile ? '14px 16px' : '15px 18px',
        boxShadow: isDark ? '0 12px 32px rgba(0, 0, 0, 0.24)' : '0 12px 32px rgba(15, 23, 42, 0.07)',
      }}
    >
      <Group justify="space-between" wrap="nowrap" gap="sm">
        <Group wrap="nowrap" gap="sm" style={{ minWidth: 0 }}>
          <Box
            style={{
              width: 42,
              height: 42,
              minWidth: 42,
              borderRadius: 14,
              display: 'grid',
              placeItems: 'center',
              background: 'linear-gradient(135deg, #0f766e 0%, #134e4a 100%)',
              color: '#ffffff',
              boxShadow: '0 10px 22px rgba(15, 118, 110, 0.25)',
            }}
          >
            <IconBriefcase2 size={20} />
          </Box>
          <Box style={{ minWidth: 0, textAlign: 'left' }}>
            <Text size="xs" tt="uppercase" fw={700} c={isDark ? theme.colors.gray[4] : '#64748b'} mb={4} style={{ letterSpacing: 0.8 }}>
              Portfolio attivo
            </Text>
            <Text fw={700} size="sm" c={isDark ? theme.white : '#0f172a'} lineClamp={1}>
              {triggerLabel}
            </Text>
            <Text size="xs" c="dimmed" lineClamp={1}>
              {triggerMeta}
            </Text>
            {selectedPortfolio && (
              <Group gap={6} mt={8} wrap="wrap">
                <Badge variant="light" color="blue" size="sm" leftSection={<IconWallet size={11} />}>
                  {formatMoney(selectedPortfolioCashBalance ?? selectedPortfolio.current_cash_balance ?? selectedPortfolio.cash_balance ?? 0, selectedPortfolio.base_currency)}
                </Badge>
                {selectedPortfolio.target_notional != null && (
                  <Badge variant="light" color="orange" size="sm" leftSection={<IconTarget size={11} />}>
                    {formatMoney(selectedPortfolio.target_notional, selectedPortfolio.base_currency)}
                  </Badge>
                )}
              </Group>
            )}
          </Box>
        </Group>
        <ActionIcon variant="subtle" color="gray" radius="xl" aria-label="Apri selettore portafogli">
          <IconChevronDown size={18} color={isDark ? theme.colors.gray[4] : '#475569'} style={{ flexShrink: 0 }} />
        </ActionIcon>
      </Group>
    </UnstyledButton>
  );

  return (
    <Box style={style}>
      {label && (
        <Text size="xs" fw={700} c={isDark ? theme.colors.gray[4] : '#475569'} mb={6} tt="uppercase" style={{ letterSpacing: 0.8 }}>
          {label}
        </Text>
      )}

      {isMobile ? (
        <>
          {trigger}
          <Drawer
            opened={opened}
            onClose={() => {
              setOpened(false);
              setQuery('');
            }}
            position="bottom"
            size="100%"
            radius="24px 24px 0 0"
            title="Seleziona portafoglio"
            styles={{
              content: { paddingBottom: 'var(--safe-area-bottom)' },
              body: { paddingBottom: 'calc(var(--mantine-spacing-md) + var(--safe-area-bottom))' },
            }}
          >
            {list}
          </Drawer>
        </>
      ) : (
        <Popover
          opened={opened}
          onChange={setOpened}
          width={420}
          position="bottom-end"
          shadow="md"
          radius="xl"
        >
          <Popover.Target>
            <Box>{trigger}</Box>
          </Popover.Target>
          <Popover.Dropdown p="md">
            {list}
          </Popover.Dropdown>
        </Popover>
      )}
    </Box>
  );
}
