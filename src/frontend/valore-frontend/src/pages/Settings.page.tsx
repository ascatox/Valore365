
import { useState } from 'react';
import {
  Tabs,
  Paper,
  Select,
  Switch,
  Group,
  NumberInput,
  Text,
  Button,
  Title,
  Stack,
  useMantineTheme,
  SegmentedControl,
  useMantineColorScheme,
  Center,
  Box,
} from '@mantine/core';
import { IconSettings, IconTarget, IconReceipt, IconShield, IconSun, IconMoon, IconDeviceDesktop } from '@tabler/icons-react';

// Mock data for target allocation
const initialAllocation = [
  { name: 'Vanguard FTSE All-World', weight: 45.14 },
  { name: 'iShares Core Corp Bond', weight: 10.53 },
  { name: 'iShares Core € Govt Bond', weight: 10.02 },
  { name: 'Liquidità', weight: 0.87 },
];

export function SettingsPage() {
  const theme = useMantineTheme();
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const [allocations, setAllocations] = useState(initialAllocation);

  const handleAllocationChange = (index: number, value: any) => {
    const newAllocations = [...allocations];
    newAllocations[index].weight = typeof value === 'number' ? value : 0;
    setAllocations(newAllocations);
  };

  const totalAllocation = allocations.reduce((sum, item) => sum + item.weight, 0);

  return (
    <Stack gap={0}>
      <Title order={2} fw={700} mb="md">Impostazioni</Title>

      <Tabs orientation="vertical" defaultValue="general" variant="pills" radius="md">
        <Tabs.List>
          <Tabs.Tab value="general" leftSection={<IconSettings size={18} />}>Generale</Tabs.Tab>
          <Tabs.Tab value="allocation" leftSection={<IconTarget size={18} />}>Target Allocation</Tabs.Tab>
          <Tabs.Tab value="tax" leftSection={<IconReceipt size={18} />}>Fiscalità</Tabs.Tab>
          <Tabs.Tab value="security" leftSection={<IconShield size={18} />}>Sicurezza</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="general">
          <Paper withBorder p="lg" radius="md" ml="md">
            <Stack gap="lg">
              <Title order={3}>Impostazioni Generali</Title>
              <Select
                label="Valuta Principale"
                defaultValue="EUR"
                data={[
                  { value: 'EUR', label: '€ Euro' },
                  { value: 'USD', label: '$ Dollaro Americano' },
                ]}
                style={{ maxWidth: 300 }}
              />
              <Switch
                label="Avvia in Privacy Mode"
                description="Se attivo, i valori monetari saranno offuscati all'avvio."
              />
              <Stack gap="xs">
                <Text fw={500} size="sm">Aspetto dell'Applicazione</Text>
                <SegmentedControl
                  value={colorScheme}
                  onChange={(value) => setColorScheme(value as 'light' | 'dark' | 'auto')}
                  data={[
                    {
                      value: 'light',
                      label: (
                        <Center>
                          <IconSun size={16} />
                          <Box ml="xs">Light</Box>
                        </Center>
                      ),
                    },
                    {
                      value: 'dark',
                      label: (
                        <Center>
                          <IconMoon size={16} />
                          <Box ml="xs">Dark</Box>
                        </Center>
                      ),
                    },
                    {
                      value: 'auto',
                      label: (
                        <Center>
                          <IconDeviceDesktop size={16} />
                          <Box ml="xs">Auto</Box>
                        </Center>
                      ),
                    },
                  ]}
                />
              </Stack>
            </Stack>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="allocation">
        <Paper withBorder p="lg" radius="md" ml="md">
            <Stack>
                <Title order={3}>Definizione Target Allocation</Title>
                {allocations.map((item, index) => (
                    <Group key={item.name} justify="space-between">
                    <Text>{item.name}</Text>
                    <NumberInput
                        value={item.weight}
                        onChange={(value) => handleAllocationChange(index, value)}
                        suffix=" %"
                        step={0.01}
                        min={0}
                        max={100}
                        style={{ width: 120 }}
                    />
                    </Group>
                ))}
                <Group justify="flex-end" mt="md">
                    <Text fw={700}>Totale:</Text>
                    <Text fw={700} c={totalAllocation.toFixed(2) !== '100.00' ? 'red' : 'teal'}>
                        {totalAllocation.toFixed(2)} %
                    </Text>
                </Group>
            </Stack>
        </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="tax">
        <Paper withBorder p="lg" radius="md" ml="md">
          <Stack>
            <Title order={3}>Impostazioni Fiscali</Title>
            <NumberInput
              label="Tassa sui Capital Gain (%)"
              defaultValue={26}
              suffix=" %"
              style={{ maxWidth: 300 }}
            />
            <NumberInput
              label="Commissioni Broker di Default (€)"
              defaultValue={1.99}
              prefix="€ "
              decimalScale={2}
              style={{ maxWidth: 300 }}
            />
          </Stack>
        </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="security">
        <Paper withBorder p="lg" radius="md" ml="md">
            <Stack>
                <Title order={3}>Sicurezza e Dati</Title>
                <Paper withBorder p="lg" style={{ borderColor: theme.colors.red[6] }}>
                    <Stack>
                        <Title order={4} c="red">Danger Zone</Title>
                        <Text>Queste azioni sono irreversibili. Procedi con cautela.</Text>
                         <Group justify="flex-start">
                            <Button>Esporta Dati in CSV</Button>
                            <Button variant="outline" color="red">
                                Elimina tutti i dati del portafoglio
                            </Button>
                        </Group>
                    </Stack>
                </Paper>
            </Stack>
        </Paper>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
