
import {
  Tabs,
  Paper,
  Select,
  Switch,
  NumberInput,
  Text,
  Button,
  Title,
  Stack,
  Group,
  useMantineTheme,
  SegmentedControl,
  useMantineColorScheme,
  Center,
  Box,
} from '@mantine/core';
import { IconSettings, IconReceipt, IconShield, IconSun, IconMoon, IconDeviceDesktop } from '@tabler/icons-react';

export function SettingsPage() {
  const theme = useMantineTheme();
  const { colorScheme, setColorScheme } = useMantineColorScheme();

  return (
    <Stack gap={0}>
      <Title order={2} fw={700} mb="md">Impostazioni</Title>

      <Tabs orientation="vertical" defaultValue="general" variant="pills" radius="md">
        <Tabs.List>
          <Tabs.Tab value="general" leftSection={<IconSettings size={18} />}>Generale</Tabs.Tab>
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
