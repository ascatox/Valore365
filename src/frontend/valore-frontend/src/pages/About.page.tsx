import { Anchor, Button, Card, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconBriefcase, IconRobot, IconShieldCheck, IconTargetArrow, IconWorld } from '@tabler/icons-react';
import { Link } from 'react-router-dom';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';

export function AboutPage() {
  return (
    <PageLayout>
      <Stack gap="xl">
        <PageHeader
          eyebrow="About"
          title="Valore365"
          description="Una dashboard personale per monitorare portafogli, analizzare la loro salute, pianificare il FIRE e usare strumenti AI di supporto."
          actions={(
            <Group gap="sm">
              <Button component={Link} to="/portfolio">
                Vai al portfolio
              </Button>
              <Button component={Link} to="/settings" variant="default">
                Impostazioni
              </Button>
            </Group>
          )}
        />

        <Card withBorder radius="xl" padding="xl">
          <Stack gap="md">
            <Title order={3}>Cosa fa</Title>
            <Text c="dimmed">
              Valore365 unisce monitoraggio patrimoniale, analisi operativa e pianificazione finanziaria in un&apos;interfaccia unica.
              L&apos;obiettivo e&apos; avere una vista leggibile del portafoglio, dei rischi principali e del percorso verso i target personali.
            </Text>
          </Stack>
        </Card>

        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
          <InfoCard
            icon={IconBriefcase}
            title="Portfolio"
            description="Gestione portafogli, posizioni, transazioni, liquidita&apos; e riepiloghi operativi in un unico flusso."
          />
          <InfoCard
            icon={IconTargetArrow}
            title="FIRE e pianificazione"
            description="Stime su capitale target, anni al FIRE, contributo richiesto e scenari di decumulo."
          />
          <InfoCard
            icon={IconRobot}
            title="Copilot"
            description="Supporto conversazionale per leggere piu&apos; rapidamente i dati del portafoglio e individuare spunti di analisi."
          />
          <InfoCard
            icon={IconShieldCheck}
            title="Controllo e privacy"
            description="Modalita&apos; privacy, impostazioni utente dedicate e separazione tra configurazione locale e servizi backend."
          />
        </SimpleGrid>

        <Card withBorder radius="xl" padding="xl">
          <Stack gap="sm">
            <Title order={4}>Per chi e&apos; pensata</Title>
            <Text c="dimmed">
              Per investitori che vogliono seguire il proprio patrimonio con piu&apos; dettaglio operativo rispetto a un semplice tracker,
              senza perdere leggibilita&apos; su mobile e senza disperdere le informazioni tra strumenti separati.
            </Text>
          </Stack>
        </Card>

        <Card withBorder radius="xl" padding="xl">
          <Stack gap="sm">
            <Group gap="sm">
              <ThemeIcon radius="xl" size="lg" color="grape" variant="light">
                <IconWorld size={18} />
              </ThemeIcon>
              <Title order={4}>Autore</Title>
            </Group>
            <Text c="dimmed">
              Valore365 e&apos; curato da <Text span fw={700} c="inherit">Antonio Scatoloni</Text>.
            </Text>
            <Anchor href="https://www.antonioscatoloni.it" target="_blank" rel="noreferrer">
              antonioscatoloni.it
            </Anchor>
          </Stack>
        </Card>
      </Stack>
    </PageLayout>
  );
}

function InfoCard({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof IconBriefcase;
  title: string;
  description: string;
}) {
  return (
    <Card withBorder radius="xl" padding="lg">
      <Stack gap="sm">
        <Group gap="sm">
          <ThemeIcon radius="xl" size="lg" color="blue" variant="light">
            <Icon size={18} />
          </ThemeIcon>
          <Text fw={700}>{title}</Text>
        </Group>
        <Text c="dimmed">{description}</Text>
      </Stack>
    </Card>
  );
}
