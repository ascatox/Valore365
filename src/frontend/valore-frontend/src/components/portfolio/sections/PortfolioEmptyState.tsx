import {
  Button,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
  useComputedColorScheme,
} from '@mantine/core';
import { IconChecklist, IconFileImport, IconPlus, IconSparkles } from '@tabler/icons-react';

interface PortfolioEmptyStateProps {
  onCreatePortfolio: () => void;
  onImportFromFile: () => void;
}

export function PortfolioEmptyState({ onCreatePortfolio, onImportFromFile }: PortfolioEmptyStateProps) {
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  return (
    <Card
      withBorder
      radius="xl"
      mb="md"
      style={{
        background: isDark
          ? 'linear-gradient(135deg, rgba(20,184,166,0.10), rgba(15,23,42,0.9))'
          : 'linear-gradient(135deg, #f8fffd 0%, #eefaf6 48%, #f8fbff 100%)',
      }}
    >
      <Stack gap="lg">
        <Group gap="sm">
          <ThemeIcon radius="xl" size={42} color="teal" variant="light">
            <IconSparkles size={22} />
          </ThemeIcon>
          <div>
            <Title order={3}>Inizia da qui</Title>
            <Text c="dimmed">
              Per partire ti basta creare il primo portfolio oppure importare uno storico da file.
            </Text>
          </div>
        </Group>

        <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
          <Card withBorder radius="lg" padding="md">
            <Group gap="sm" mb="xs">
              <ThemeIcon radius="xl" size={32} color="blue" variant="light">
                <IconPlus size={18} />
              </ThemeIcon>
              <Text fw={600}>1. Crea il portfolio</Text>
            </Group>
            <Text size="sm" c="dimmed">
              Imposta nome, valuta base e timezone del portafoglio che userai come contenitore iniziale.
            </Text>
          </Card>

          <Card withBorder radius="lg" padding="md">
            <Group gap="sm" mb="xs">
              <ThemeIcon radius="xl" size={32} color="teal" variant="light">
                <IconFileImport size={18} />
              </ThemeIcon>
              <Text fw={600}>2. Importa o inserisci</Text>
            </Group>
            <Text size="sm" c="dimmed">
              Puoi importare da Fineco o da file generico, oppure aggiungere le prime transazioni manualmente.
            </Text>
          </Card>

          <Card withBorder radius="lg" padding="md">
            <Group gap="sm" mb="xs">
              <ThemeIcon radius="xl" size={32} color="orange" variant="light">
                <IconChecklist size={18} />
              </ThemeIcon>
              <Text fw={600}>3. Controlla il risultato</Text>
            </Group>
            <Text size="sm" c="dimmed">
              Dopo il primo caricamento puoi rivedere transazioni, liquidita e allocazione target dalla stessa pagina.
            </Text>
          </Card>
        </SimpleGrid>

        <Group gap="sm">
          <Button leftSection={<IconPlus size={16} />} onClick={onCreatePortfolio}>
            Crea portfolio
          </Button>
          <Button variant="light" leftSection={<IconFileImport size={16} />} onClick={onImportFromFile}>
            Importa da file
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
