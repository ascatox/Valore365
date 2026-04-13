import { Button, Card, Group, Text, useMantineTheme, useComputedColorScheme } from '@mantine/core';
import { formatNum } from '../dashboard/formatters';
import { formatMoneyOrNA, formatDateTime, formatTransactionSideLabel, getTransactionSideColor } from '../dashboard/formatters';

interface TransactionMobileCardProps {
  id: number;
  symbol: string;
  assetName?: string | null;
  side: string;
  tradeAt: string;
  quantity: number;
  price: number;
  fees: number;
  taxes: number;
  tradeCurrency: string;
  notes?: string | null;
  deleting?: boolean;
  onEdit: () => void;
  onDelete: () => void;
}

export function TransactionMobileCard({
  symbol,
  assetName,
  side,
  tradeAt,
  quantity,
  price,
  fees,
  taxes,
  tradeCurrency,
  notes,
  deleting,
  onEdit,
  onDelete,
}: TransactionMobileCardProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  const gross = quantity * price;
  const total = side === 'buy'
    ? gross + fees + taxes
    : gross - fees - taxes;
  const sideColor = getTransactionSideColor(side);

  const sideBackgrounds: Record<string, string> = {
    teal: 'rgba(13,148,136,0.12)',
    orange: 'rgba(249,115,22,0.12)',
    blue: 'rgba(59,130,246,0.12)',
    gray: 'rgba(107,114,128,0.12)',
  };

  return (
    <Card
      withBorder
      radius="xl"
      p="lg"
      style={{
        background: isDark
          ? `linear-gradient(180deg, ${theme.colors.dark[7]} 0%, ${theme.colors.dark[6]} 100%)`
          : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
        boxShadow: isDark ? '0 18px 36px rgba(0, 0, 0, 0.24)' : '0 18px 36px rgba(15, 23, 42, 0.08)',
      }}
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
        <div style={{ minWidth: 0 }}>
          <Group gap={8} wrap="wrap" mb={4}>
            <Text fw={800} size="lg">{symbol}</Text>
            <Text
              fw={700}
              size="xs"
              c={sideColor}
              style={{
                padding: '6px 10px',
                borderRadius: 999,
                background: sideBackgrounds[sideColor] ?? sideBackgrounds.gray,
              }}
            >
              {formatTransactionSideLabel(side)}
            </Text>
          </Group>
          {assetName ? <Text size="xs" c="dimmed">{assetName}</Text> : null}
        </div>
        <Card radius="lg" p="sm" style={{ minWidth: 110, background: isDark ? 'rgba(15,118,110,0.15)' : 'rgba(15,118,110,0.06)', border: isDark ? `1px solid ${theme.colors.teal[8]}` : '1px solid rgba(15,118,110,0.12)' }}>
          <Text size="xs" fw={700} tt="uppercase" c={isDark ? theme.colors.teal[4] : '#0f766e'} style={{ letterSpacing: 0.8 }}>Valore</Text>
          <Text fw={800} size="sm">{formatMoneyOrNA(total, tradeCurrency)}</Text>
        </Card>
      </Group>

      <Text size="xs" c="dimmed" mt={8}>{formatDateTime(tradeAt)}</Text>

      <Group grow mt="md">
        <Card radius="lg" p="sm" bg={isDark ? theme.colors.dark[6] : '#f8fafc'} withBorder>
          <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: 0.8 }}>Quantita'</Text>
          <Text fw={700} size="sm">{formatNum(quantity, 4)}</Text>
        </Card>
        <Card radius="lg" p="sm" bg={isDark ? theme.colors.dark[6] : '#f8fafc'} withBorder>
          <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: 0.8 }}>Prezzo</Text>
          <Text fw={700} size="sm">{formatMoneyOrNA(price, tradeCurrency)}</Text>
        </Card>
      </Group>
      <Group grow mt="xs">
        <Card radius="lg" p="sm" bg={isDark ? theme.colors.dark[6] : '#f8fafc'} withBorder>
          <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: 0.8 }}>Fee</Text>
          <Text fw={700} size="sm">{formatMoneyOrNA(fees, tradeCurrency)}</Text>
        </Card>
        <Card radius="lg" p="sm" bg={isDark ? theme.colors.dark[6] : '#f8fafc'} withBorder>
          <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: 0.8 }}>Lordo</Text>
          <Text fw={700} size="sm">{formatMoneyOrNA(gross, tradeCurrency)}</Text>
        </Card>
      </Group>
      {!!notes && (
        <Card radius="lg" p="sm" mt="sm" bg={isDark ? 'rgba(251,191,36,0.08)' : '#fff7ed'} style={{ border: isDark ? `1px solid ${theme.colors.yellow[8]}` : '1px solid #fed7aa' }}>
          <Text size="xs" fw={700} tt="uppercase" c={isDark ? theme.colors.yellow[4] : '#9a3412'} style={{ letterSpacing: 0.8 }}>Note</Text>
          <Text size="sm" c={isDark ? theme.colors.yellow[3] : '#7c2d12'}>{notes}</Text>
        </Card>
      )}
      <Group grow mt="sm">
        <Button variant="default" radius="xl" onClick={onEdit}>
          Modifica
        </Button>
        <Button
          color="red"
          variant="light"
          radius="xl"
          onClick={onDelete}
          loading={deleting}
        >
          Elimina
        </Button>
      </Group>
    </Card>
  );
}
