
import { useEffect, useState } from 'react';
import {
  Badge,
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
    <Stack gap={isMobile ? 'xs' : 0}>
      {isMobile ? (
        <Group justify="space-between" mb="xs" align="flex-end" wrap="wrap" gap="xs">
          <Title order={4} fw={800}>Impostazioni</Title>
        </Group>
      ) : (
        <Title order={2} fw={700} mb="md">Impostazioni</Title>
      )}

      <Tabs orientation={isMobile ? 'horizontal' : 'vertical'} defaultValue="general" variant="pills" radius="md">
        <Tabs.List
          style={isMobile ? {
            display: 'grid',
            gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
            gap: 8,
            padding: 8,
            background: colorScheme === 'dark' ? 'rgba(30,41,59,0.9)' : 'rgba(255,255,255,0.9)',
            border: colorScheme === 'dark' ? `1px solid ${theme.colors.dark[4]}` : '1px solid rgba(148,163,184,0.18)',
            borderRadius: 20,
            boxShadow: colorScheme === 'dark' ? '0 14px 30px rgba(0, 0, 0, 0.24)' : '0 14px 30px rgba(15, 23, 42, 0.08)',
          } : undefined}
        >
          <Tabs.Tab value="general" leftSection={<IconSettings size={18} />}>Generale</Tabs.Tab>
          <Tabs.Tab value="tax" leftSection={<IconReceipt size={18} />}>Fiscalità</Tabs.Tab>
          <Tabs.Tab value="security" leftSection={<IconShield size={18} />}>Sicurezza</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="general">
          <Paper
            withBorder
            p="lg"
            radius={isMobile ? 'xl' : 'md'}
            ml={isMobile ? 0 : 'md'}
            mt={isMobile ? 'md' : 0}
            style={isMobile ? {
              background: colorScheme === 'dark'
                ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
                : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
              boxShadow: colorScheme === 'dark' ? '0 18px 36px rgba(0, 0, 0, 0.28)' : '0 18px 36px rgba(15, 23, 42, 0.08)',
            } : undefined}
          >
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
        <Paper
          withBorder
          p="lg"
          radius={isMobile ? 'xl' : 'md'}
          ml={isMobile ? 0 : 'md'}
          mt={isMobile ? 'md' : 0}
          style={isMobile ? {
            background: colorScheme === 'dark'
              ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
              : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
            boxShadow: colorScheme === 'dark' ? '0 18px 36px rgba(0, 0, 0, 0.28)' : '0 18px 36px rgba(15, 23, 42, 0.08)',
          } : undefined}
        >
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
        <Paper
          withBorder
          p="lg"
          radius={isMobile ? 'xl' : 'md'}
          ml={isMobile ? 0 : 'md'}
          mt={isMobile ? 'md' : 0}
          style={isMobile ? {
            background: colorScheme === 'dark'
              ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
              : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
            boxShadow: colorScheme === 'dark' ? '0 18px 36px rgba(0, 0, 0, 0.28)' : '0 18px 36px rgba(15, 23, 42, 0.08)',
          } : undefined}
        >
            <Stack>
                <Title order={3}>Sicurezza e Dati</Title>
                <Paper
                  withBorder
                  p="lg"
                  radius={isMobile ? 'xl' : 'md'}
                  style={{
                    borderColor: theme.colors.red[6],
                    background: isMobile
                      ? (colorScheme === 'dark'
                        ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
                        : 'linear-gradient(180deg, #fff7f7 0%, #ffffff 100%)')
                      : undefined,
                  }}
                >
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
