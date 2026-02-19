import React from 'react';
import { SimpleGrid, Paper, Text, Group, RingProgress, Badge, Table, Card, ThemeIcon, Grid } from '@mantine/core';
import { IconArrowUpRight, IconArrowDownRight, IconCoin, IconChartPie, IconActivity, IconReceiptTax } from '@tabler/icons-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

// --- MOCK DATA (Basati sul tuo portafoglio reale) ---
const KPI_DATA = [
  { label: 'Patrimonio Netto', amount: '€ 124.500,00', diff: 1.2, icon: IconCoin, color: 'blue' },
  { label: 'P&L Giornaliero', amount: '+ € 1.450,00', diff: 1.15, icon: IconActivity, color: 'teal' },
  { label: 'P&L Totale', amount: '+ € 12.300,00', diff: 14.5, icon: IconArrowUpRight, color: 'green' },
  { label: 'Costi Annui (TER)', amount: '€ 215,00', diff: -0.18, icon: IconReceiptTax, color: 'orange' }, // Media ponderata
];

const CHART_DATA = [
  { date: 'Gen', value: 110000 }, { date: 'Feb', value: 112000 }, { date: 'Mar', value: 108000 },
  { date: 'Apr', value: 115000 }, { date: 'Mag', value: 119000 }, { date: 'Giu', value: 124500 },
];

const ALLOCATION_DATA = [
  { value: 45, color: 'blue', tooltip: 'Azionario (Vanguard/World)' },
  { value: 35, color: 'cyan', tooltip: 'Obbligazionario (Gov/Corp)' },
  { value: 4, color: 'yellow', tooltip: 'Oro (ETC)' },
  { value: 16, color: 'gray', tooltip: 'Liquidità & Altro' },
];

const TOP_MOVERS = [
  { name: 'Vanguard FTSE All-World', ticker: 'VWCE', change: 1.8, price: '€ 112,40' },
  { name: 'iShares Core Corp Bond', ticker: 'IEAC', change: -0.4, price: '€ 124,10' },
  { name: 'Xtrackers Physical Gold', ticker: 'XGDU', change: 0.9, price: '€ 180,50' },
];

// --- COMPONENTI ---

export function DashboardPage() {
  
  // 1. Le Card in alto (Statistiche)
  const stats = KPI_DATA.map((stat) => {
    const DiffIcon = stat.diff > 0 ? IconArrowUpRight : IconArrowDownRight;
    const diffColor = stat.diff > 0 ? 'teal' : 'red';

    return (
      <Paper withBorder p="md" radius="md" key={stat.label} shadow="xs">
        <Group justify="space-between">
          <Text size="xs" c="dimmed" fw={700} tt="uppercase">
            {stat.label}
          </Text>
          <ThemeIcon color={stat.color} variant="light" size="md" radius="md">
            <stat.icon size={18} />
          </ThemeIcon>
        </Group>

        <Group align="flex-end" gap="xs" mt={25}>
          <Text fw={700} size="xl">{stat.amount}</Text>
          <Badge color={diffColor} variant="light" size="sm" leftSection={<DiffIcon size={12}/>}>
            {stat.diff}%
          </Badge>
        </Group>
      </Paper>
    );
  });

  // 2. Tabella Movimenti Rapidi
  const rows = TOP_MOVERS.map((element) => (
    <Table.Tr key={element.ticker}>
      <Table.Td>
        <Text size="sm" fw={500}>{element.ticker}</Text>
        <Text size="xs" c="dimmed">{element.name}</Text>
      </Table.Td>
      <Table.Td align="right">{element.price}</Table.Td>
      <Table.Td align="right">
        <Text c={element.change > 0 ? 'teal' : 'red'} size="sm" fw={500}>
          {element.change > 0 ? '+' : ''}{element.change}%
        </Text>
      </Table.Td>
    </Table.Tr>
  ));

  return (
    <div style={{ padding: '20px' }}>
      
      {/* SEZIONE 1: KPI CARDS */}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md" mb="lg">
        {stats}
      </SimpleGrid>

      <Grid gutter="md">
        
        {/* SEZIONE 2: GRAFICO STORICO (Area Chart) */}
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Card withBorder radius="md" p="md" shadow="sm">
            <Text fw={500} mb="md">Andamento Portafoglio (YTD)</Text>
            <div style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={CHART_DATA}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#228be6" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#228be6" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e0e0e0" />
                  <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{fill: '#868e96', fontSize: 12}} />
                  <YAxis hide domain={['auto', 'auto']} />
                  <Tooltip 
                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} 
                    itemStyle={{ color: '#228be6', fontWeight: 600 }}
                  />
                  <Area type="monotone" dataKey="value" stroke="#228be6" strokeWidth={3} fillOpacity={1} fill="url(#colorValue)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </Grid.Col>

        {/* SEZIONE 3: ALLOCAZIONE & TOP MOVERS */}
        <Grid.Col span={{ base: 12, md: 4 }}>
            {/* Allocazione Asset */}
            <Card withBorder radius="md" p="md" mb="md" shadow="sm">
                <Text fw={500} mb="xs">Allocazione Asset</Text>
                <Group justify="center">
                    <RingProgress
                        size={180}
                        thickness={16}
                        roundCaps
                        sections={ALLOCATION_DATA}
                        label={
                            <Text c="blue" fw={700} ta="center" size="xl">
                                100%
                            </Text>
                        }
                    />
                </Group>
                <Group justify="center" mt="xs" gap="xs">
                    <Badge color="blue" size="sm" variant="dot">Equity</Badge>
                    <Badge color="cyan" size="sm" variant="dot">Bond</Badge>
                    <Badge color="yellow" size="sm" variant="dot">Gold</Badge>
                </Group>
            </Card>

            {/* Top Movers Table */}
            <Card withBorder radius="md" p="0" shadow="sm">
                <Table verticalSpacing="xs" striped highlightOnHover>
                    <Table.Thead>
                        <Table.Tr>
                            <Table.Th>Asset</Table.Th>
                            <Table.Th style={{textAlign: 'right'}}>Prezzo</Table.Th>
                            <Table.Th style={{textAlign: 'right'}}>%</Table.Th>
                        </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>{rows}</Table.Tbody>
                </Table>
            </Card>
        </Grid.Col>

      </Grid>
    </div>
  );
}