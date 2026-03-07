
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
  useComputedColorScheme,
  Center,
  Box,
  Alert,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconSettings, IconReceipt, IconShield, IconSun, IconMoon, IconDeviceDesktop, IconRobot } from '@tabler/icons-react';
import { MobileBottomNav } from '../components/mobile/MobileBottomNav';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { getUserSettings, updateUserSettings, getCopilotStatus } from '../services/api';
import type { CopilotStatus } from '../services/api';

export function SettingsPage() {
  const theme = useMantineTheme();
  const { colorScheme: colorSchemeRaw, setColorScheme } = useMantineColorScheme();
  const colorScheme = useComputedColorScheme('light');
  const isMobile = useMediaQuery('(max-width: 48em)');
  const [activeTab, setActiveTab] = useState('general');
  const [brokerDefaultFee, setBrokerDefaultFee] = useState<number | string>(1.99);
  const [privacyModeEnabled, setPrivacyModeEnabled] = useState(false);
  const [settingsSavedMessage, setSettingsSavedMessage] = useState<string | null>(null);

  // Copilot settings
  const [copilotProvider, setCopilotProvider] = useState('');
  const [copilotModel, setCopilotModel] = useState('');
  const [copilotApiKey, setCopilotApiKey] = useState('');
  const [copilotApiKeySet, setCopilotApiKeySet] = useState(false);
  const [copilotStatus, setCopilotStatus] = useState<CopilotStatus | null>(null);
  const [copilotSaving, setCopilotSaving] = useState(false);
  const [copilotMessage, setCopilotMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    if (typeof window !== 'undefined') {
      const rawPrivacy = window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled);
      setPrivacyModeEnabled(rawPrivacy === 'true');
    }

    getUserSettings()
      .then((s) => {
        if (!active) return;
        const fee = Number(s.broker_default_fee ?? 0);
        if (Number.isFinite(fee) && fee >= 0) {
          setBrokerDefaultFee(fee);
          if (typeof window !== 'undefined') {
            window.localStorage.setItem(STORAGE_KEYS.brokerDefaultFee, String(fee));
          }
        }
        setCopilotProvider(s.copilot_provider || '');
        setCopilotModel(s.copilot_model || '');
        setCopilotApiKeySet(s.copilot_api_key_set);
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

    getCopilotStatus().then((st) => { if (active) setCopilotStatus(st); }).catch(() => {});

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

  const handleSaveCopilotSettings = () => {
    setCopilotSaving(true);
    setCopilotMessage(null);
    const payload: Record<string, string | undefined> = {
      copilot_provider: copilotProvider,
      copilot_model: copilotModel,
    };
    // Only send API key if user typed something new (or explicitly cleared it)
    if (copilotApiKey !== '') {
      payload.copilot_api_key = copilotApiKey;
    } else if (!copilotApiKeySet && copilotProvider) {
      // Provider set but no key — user needs to provide one
      setCopilotMessage('Inserisci una chiave API per il provider selezionato');
      setCopilotSaving(false);
      return;
    }
    updateUserSettings(payload as any)
      .then((saved) => {
        setCopilotApiKeySet(saved.copilot_api_key_set);
        setCopilotApiKey('');
        setCopilotMessage('Impostazioni Copilot salvate');
        getCopilotStatus().then(setCopilotStatus).catch(() => {});
      })
      .catch((err) => {
        setCopilotMessage(err instanceof Error ? err.message : 'Errore salvataggio');
      })
      .finally(() => setCopilotSaving(false));
  };

  const handleClearCopilotKey = () => {
    setCopilotSaving(true);
    setCopilotMessage(null);
    updateUserSettings({ copilot_provider: '', copilot_model: '', copilot_api_key: '' } as any)
      .then((saved) => {
        setCopilotProvider('');
        setCopilotModel('');
        setCopilotApiKey('');
        setCopilotApiKeySet(false);
        setCopilotMessage('Chiave API rimossa');
        getCopilotStatus().then(setCopilotStatus).catch(() => {});
      })
      .catch((err) => {
        setCopilotMessage(err instanceof Error ? err.message : 'Errore');
      })
      .finally(() => setCopilotSaving(false));
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

  const mobileTabItems = [
    { value: 'general', label: 'Generale', icon: IconSettings },
    { value: 'copilot', label: 'Copilot', icon: IconRobot },
    { value: 'tax', label: 'Fiscalità', icon: IconReceipt },
    { value: 'security', label: 'Sicurezza', icon: IconShield },
  ];

  return (
    <Box
      style={{
        paddingBottom: isMobile ? 104 : undefined,
        background: isMobile
          ? (colorScheme === 'dark'
            ? `linear-gradient(180deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[7]} 22%, transparent 42%)`
            : 'linear-gradient(180deg, #f8fafc 0%, #ffffff 22%, transparent 42%)')
          : undefined,
        minHeight: '100%',
      }}
    >
    <Stack gap={isMobile ? 'xs' : 0}>
      {isMobile ? (
        <Group justify="space-between" mb="xs" align="flex-end" wrap="wrap" gap="xs">
          <Title order={4} fw={800}>Impostazioni</Title>
        </Group>
      ) : (
        <Title order={2} fw={700} mb="md">Impostazioni</Title>
      )}

      <Tabs orientation={isMobile ? 'horizontal' : 'vertical'} value={activeTab} onChange={(v) => setActiveTab(v ?? 'general')} variant="pills" radius="md">
        {!isMobile && (
        <Tabs.List>
          <Tabs.Tab value="general" leftSection={<IconSettings size={18} />}>Generale</Tabs.Tab>
          <Tabs.Tab value="copilot" leftSection={<IconRobot size={18} />}>Copilot</Tabs.Tab>
          <Tabs.Tab value="tax" leftSection={<IconReceipt size={18} />}>Fiscalità</Tabs.Tab>
          <Tabs.Tab value="security" leftSection={<IconShield size={18} />}>Sicurezza</Tabs.Tab>
        </Tabs.List>
        )}

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
                  value={colorSchemeRaw}
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

        <Tabs.Panel value="copilot">
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
              <Title order={3}>Portfolio Copilot</Title>
              <Text size="sm" c="dimmed">
                Inserisci la tua chiave API per abilitare il chatbot AI. La chiave viene cifrata e non è mai visibile dopo il salvataggio.
              </Text>

              {copilotMessage && (
                <Alert color={copilotMessage.includes('Errore') || copilotMessage.includes('Inserisci') ? 'red' : 'teal'}>
                  {copilotMessage}
                </Alert>
              )}

              {copilotStatus && (
                <Badge
                  variant="light"
                  color={copilotStatus.available ? 'green' : 'gray'}
                  size="lg"
                >
                  {copilotStatus.available
                    ? `Attivo: ${copilotStatus.provider} / ${copilotStatus.model} (${copilotStatus.source === 'user' ? 'chiave personale' : 'chiave server'})`
                    : 'Non configurato'}
                </Badge>
              )}

              <Select
                label="Provider LLM"
                placeholder="Seleziona provider"
                value={copilotProvider || null}
                onChange={(value) => setCopilotProvider(value ?? '')}
                data={[
                  { value: 'openai', label: 'OpenAI (GPT-4o, GPT-4o-mini, ...)' },
                  { value: 'anthropic', label: 'Anthropic (Claude Sonnet, Haiku, ...)' },
                  { value: 'gemini', label: 'Google Gemini (Gemini 2.0 Flash, ...)' },
                ]}
                clearable
                style={{ maxWidth: 400 }}
              />

              <TextInput
                label="Modello (opzionale)"
                placeholder="Lascia vuoto per il default del provider"
                value={copilotModel}
                onChange={(e) => setCopilotModel(e.currentTarget.value)}
                description={copilotProvider === 'openai' ? 'Default: gpt-4o-mini' : copilotProvider === 'anthropic' ? 'Default: claude-sonnet-4-20250514' : copilotProvider === 'gemini' ? 'Default: gemini-2.0-flash' : ''}
                style={{ maxWidth: 400 }}
              />

              <TextInput
                label="Chiave API"
                placeholder={copilotApiKeySet ? '••••••••  (già configurata)' : 'sk-... / Inserisci la tua chiave'}
                value={copilotApiKey}
                onChange={(e) => setCopilotApiKey(e.currentTarget.value)}
                type="password"
                style={{ maxWidth: 400 }}
              />

              <Group justify="flex-start" gap="sm">
                <Button
                  onClick={handleSaveCopilotSettings}
                  loading={copilotSaving}
                  disabled={!copilotProvider}
                >
                  Salva impostazioni Copilot
                </Button>
                {copilotApiKeySet && (
                  <Button
                    variant="outline"
                    color="red"
                    onClick={handleClearCopilotKey}
                    loading={copilotSaving}
                  >
                    Rimuovi chiave API
                  </Button>
                )}
              </Group>
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

      {isMobile && (
        <MobileBottomNav
          items={mobileTabItems}
          value={activeTab}
          onChange={setActiveTab}
        />
      )}
    </Box>
  );
}
