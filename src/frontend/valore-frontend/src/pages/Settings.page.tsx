
import { useEffect, useState } from 'react';
import {
  Tabs,
  Paper,
  Select,
  Switch,
  NumberInput,
  TextInput,
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
  Alert,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconSettings, IconReceipt, IconShield, IconSun, IconMoon, IconDeviceDesktop } from '@tabler/icons-react';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { getUserSettings, updateUserSettings } from '../services/api';

export function SettingsPage() {
  const theme = useMantineTheme();
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const isMobile = useMediaQuery('(max-width: 48em)');
  const [brokerDefaultFee, setBrokerDefaultFee] = useState<number | string>(1.99);
  const [privacyModeEnabled, setPrivacyModeEnabled] = useState(false);
  const [settingsSavedMessage, setSettingsSavedMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    if (typeof window !== 'undefined') {
      const rawPrivacy = window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled);
      setPrivacyModeEnabled(rawPrivacy === 'true');
    }

    getUserSettings()
      .then((settings) => {
        if (!active) return;
        const fee = Number(settings.broker_default_fee ?? 0);
        if (Number.isFinite(fee) && fee >= 0) {
          setBrokerDefaultFee(fee);
          if (typeof window !== 'undefined') {
            window.localStorage.setItem(STORAGE_KEYS.brokerDefaultFee, String(fee));
          }
        }
      })
      .catch(() => {
        if (!active || typeof window === 'undefined') return;
        const raw = window.localStorage.getItem(STORAGE_KEYS.brokerDefaultFee);
        if (raw == null || raw === '') return;
        const parsed = Number(raw);
        if (Number.isFinite(parsed) && parsed >= 0) {
          setBrokerDefaultFee(parsed);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const handlePrivacyModeChange = (checked: boolean) => {
    setPrivacyModeEnabled(checked);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, String(checked));
    }
  };

  const handleSaveTaxSettings = () => {
    const fee = typeof brokerDefaultFee === 'number' ? brokerDefaultFee : Number(brokerDefaultFee);
    if (!Number.isFinite(fee) || fee < 0) {
      setSettingsSavedMessage('Commissioni broker predefinite non valide');
      return;
    }
    updateUserSettings({ broker_default_fee: fee })
      .then((saved) => {
        const normalized = Number(saved.broker_default_fee ?? fee);
        setBrokerDefaultFee(normalized);
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(STORAGE_KEYS.brokerDefaultFee, String(normalized));
        }
        setSettingsSavedMessage('Impostazioni fiscali salvate');
      })
      .catch((err) => {
        setSettingsSavedMessage(err instanceof Error ? err.message : 'Errore salvataggio impostazioni fiscali');
      });
  };

  return (
    <Stack gap={0}>
      <Title order={2} fw={700} mb="md">Impostazioni</Title>

      <Tabs orientation={isMobile ? 'horizontal' : 'vertical'} defaultValue="general" variant="pills" radius="md">
        <Tabs.List>
          <Tabs.Tab value="general" leftSection={<IconSettings size={18} />}>Generale</Tabs.Tab>
          <Tabs.Tab value="tax" leftSection={<IconReceipt size={18} />}>Fiscalità</Tabs.Tab>
          <Tabs.Tab value="security" leftSection={<IconShield size={18} />}>Sicurezza</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="general">
          <Paper withBorder p="lg" radius="md" ml={isMobile ? 0 : 'md'} mt={isMobile ? 'md' : 0}>
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
                label="Avvia in modalità privacy"
                description="Se attivo, i valori monetari saranno offuscati all'avvio."
                checked={privacyModeEnabled}
                onChange={(event) => handlePrivacyModeChange(event.currentTarget.checked)}
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
                          <Box ml="xs">Chiaro</Box>
                        </Center>
                      ),
                    },
                    {
                      value: 'dark',
                      label: (
                        <Center>
                          <IconMoon size={16} />
                          <Box ml="xs">Scuro</Box>
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
        <Paper withBorder p="lg" radius="md" ml={isMobile ? 0 : 'md'} mt={isMobile ? 'md' : 0}>
          <Stack>
            <Title order={3}>Impostazioni Fiscali</Title>
            {settingsSavedMessage && <Alert color={settingsSavedMessage.includes('non valide') ? 'red' : 'teal'}>{settingsSavedMessage}</Alert>}
            {privacyModeEnabled ? (
              <>
                <TextInput
                  label="Tassa sulle plusvalenze (%)"
                  value="******"
                  readOnly
                  style={{ maxWidth: 300 }}
                />
                <TextInput
                  label="Commissioni broker predefinite (€)"
                  value="******"
                  readOnly
                  style={{ maxWidth: 300 }}
                />
              </>
            ) : (
              <>
                <NumberInput
                  label="Tassa sulle plusvalenze (%)"
                  defaultValue={26}
                  suffix=" %"
                  style={{ maxWidth: 300 }}
                />
                <NumberInput
                  label="Commissioni broker predefinite (€)"
                  value={brokerDefaultFee}
                  onChange={(value) => {
                    setBrokerDefaultFee(value);
                    if (settingsSavedMessage) setSettingsSavedMessage(null);
                  }}
                  prefix="€ "
                  decimalScale={2}
                  style={{ maxWidth: 300 }}
                />
              </>
            )}
            <Group justify="flex-start">
              <Button onClick={handleSaveTaxSettings}>Salva impostazioni fiscali</Button>
            </Group>
          </Stack>
        </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="security">
        <Paper withBorder p="lg" radius="md" ml={isMobile ? 0 : 'md'} mt={isMobile ? 'md' : 0}>
            <Stack>
                <Title order={3}>Sicurezza e Dati</Title>
                <Paper withBorder p="lg" style={{ borderColor: theme.colors.red[6] }}>
                    <Stack>
                        <Title order={4} c="red">Area critica</Title>
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
