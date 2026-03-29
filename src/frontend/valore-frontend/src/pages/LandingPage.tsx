import { Box, Button, Card, Container, Grid, Group, SimpleGrid, Stack, Text, ThemeIcon, Title, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import {
  IconArrowRight,
  IconBolt,
  IconChartDonut3,
  IconMessageCircle2,
  IconShieldCheck,
  IconSparkles,
  IconTargetArrow,
  IconUsers,
} from '@tabler/icons-react';
import { Link } from 'react-router-dom';
import logoMark from '../assets/logo-mark.svg';

const PROBLEM_POINTS = [
  'sei davvero diversificato',
  'quanto rischio stai prendendo',
  'se stai facendo errori invisibili',
];

const HOW_IT_WORKS = [
  {
    step: '1',
    title: 'Collega',
    description: 'Importa il tuo portafoglio in pochi secondi e centralizza le posizioni in un unico posto.',
    icon: IconSparkles,
  },
  {
    step: '2',
    title: 'Capisci',
    description: "L'AI analizza struttura, rischio, overlap e costi e te li spiega in modo leggibile.",
    icon: IconChartDonut3,
  },
  {
    step: '3',
    title: 'Decidi',
    description: 'Confrontati con un mentor e prendi decisioni migliori senza farti guidare da consigli generici.',
    icon: IconUsers,
  },
];

const BENEFITS = [
  {
    title: 'Piu chiarezza',
    description: 'Capisci cosa hai in portafoglio e perche.',
    icon: IconTargetArrow,
  },
  {
    title: 'Meno errori',
    description: 'Scopri rischi nascosti prima che sia troppo tardi.',
    icon: IconShieldCheck,
  },
  {
    title: 'Piu consapevolezza',
    description: 'Non segui consigli: impari a ragionare.',
    icon: IconBolt,
  },
  {
    title: 'Supporto umano',
    description: 'Parla con qualcuno che ti spiega davvero le cose.',
    icon: IconMessageCircle2,
  },
];

export function LandingPage() {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');

  const emerald = '#10b981';
  const emeraldDark = '#059669';
  const emeraldLight = '#ecfdf5';
  const emeraldBorder = '#a7f3d0';
  const softBackground = isDark ? theme.colors.dark[7] : '#f8fafc';

  return (
    <Box style={{ minHeight: '100vh', background: isDark ? theme.colors.dark[8] : '#ffffff' }}>
      <Box
        component="header"
        style={{
          borderBottom: isDark ? `1px solid ${theme.colors.dark[5]}` : '1px solid #e5e7eb',
          background: isDark ? theme.colors.dark[7] : 'rgba(255,255,255,0.85)',
          backdropFilter: 'blur(12px)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        <Container size="1200" px={isMobile ? 'md' : 'xl'}>
          <Group justify="space-between" h={64} wrap="nowrap">
            <Group gap="sm" wrap="nowrap">
              <Box
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  background: isDark ? theme.colors.dark[5] : emeraldLight,
                  border: isDark ? `1px solid ${theme.colors.dark[4]}` : `1px solid ${emeraldBorder}`,
                  padding: 4,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <img src={logoMark} alt="Valore365" style={{ width: 24, height: 24 }} />
              </Box>
              <Text fw={800} size="lg" c={isDark ? 'white' : '#111827'}>
                Valore365
              </Text>
            </Group>

            <Group gap="sm" wrap="nowrap">
              {!isMobile && (
                <Button component={Link} to="/dashboard" variant="subtle" color="gray" radius="xl">
                  Dashboard
                </Button>
              )}
              <Button component={Link} to="/instant-analyzer" color="teal" radius="xl">
                Prova l analyzer
              </Button>
            </Group>
          </Group>
        </Container>
      </Box>

      <Box
        style={{
          background: isDark
            ? theme.colors.dark[8]
            : 'linear-gradient(180deg, #f0fdf4 0%, #ffffff 100%)',
          paddingTop: isMobile ? 56 : 88,
          paddingBottom: isMobile ? 56 : 88,
        }}
      >
        <Container size="1100" px={isMobile ? 'md' : 'xl'}>
          <Stack gap="xl" align="center" style={{ textAlign: 'center' }}>
            <Group
              gap={6}
              style={{
                background: isDark ? 'rgba(16, 185, 129, 0.1)' : 'rgba(16, 185, 129, 0.08)',
                border: isDark ? '1px solid rgba(16, 185, 129, 0.2)' : `1px solid ${emeraldBorder}`,
                borderRadius: 999,
                padding: '6px 16px',
              }}
            >
              <IconSparkles size={16} color={emerald} />
              <Text fw={700} size="sm" c={isDark ? theme.colors.teal[3] : emeraldDark}>
                AI + supporto umano
              </Text>
            </Group>

            <Title
              order={1}
              c={isDark ? 'white' : '#111827'}
              style={{
                fontSize: isMobile ? '2.2rem' : 'clamp(3.2rem, 5vw, 4.6rem)',
                lineHeight: 1.08,
                letterSpacing: '-0.04em',
                maxWidth: 900,
              }}
            >
              Capisci davvero i tuoi investimenti,
              <br />
              senza farti dire cosa comprare.
            </Title>

            <Text
              size={isMobile ? 'md' : 'lg'}
              c={isDark ? theme.colors.gray[4] : '#4b5563'}
              maw={760}
              style={{ lineHeight: 1.7 }}
            >
              Analizza il tuo portafoglio, scopri errori nascosti e prendi decisioni
              consapevoli con AI + supporto umano.
            </Text>

            <Stack gap="sm" align="center">
              <Button
                component={Link}
                to="/instant-analyzer"
                color="teal"
                size="lg"
                radius="xl"
                rightSection={<IconArrowRight size={18} />}
              >
                Inizia gratis
              </Button>
              <Text size="sm" c={isDark ? theme.colors.gray[5] : '#6b7280'}>
                Nessuna carta di credito • Nessun consiglio finanziario
              </Text>
            </Stack>
          </Stack>
        </Container>
      </Box>

      <Box py={isMobile ? 56 : 76} bg={softBackground}>
        <Container size="980" px={isMobile ? 'md' : 'xl'}>
          <Stack gap="lg" align="center" style={{ textAlign: 'center' }}>
            <Title order={2} c={isDark ? 'white' : '#111827'} style={{ fontSize: isMobile ? '1.8rem' : '2.5rem' }}>
              Stai investendo... ma sai davvero cosa stai facendo?
            </Title>
            <Text c={isDark ? theme.colors.gray[4] : '#4b5563'} maw={720} style={{ lineHeight: 1.7 }}>
              Hai ETF, azioni o fondi. Ma spesso non sai:
            </Text>
            <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md" w="100%">
              {PROBLEM_POINTS.map((point) => (
                <Card key={point} withBorder radius="xl" padding="lg" bg={isDark ? theme.colors.dark[6] : '#ffffff'}>
                  <Group align="flex-start" wrap="nowrap">
                    <ThemeIcon color="orange" variant="light" radius="xl" mt={2}>
                      <IconShieldCheck size={16} />
                    </ThemeIcon>
                    <Text fw={600} ta="left">{point}</Text>
                  </Group>
                </Card>
              ))}
            </SimpleGrid>
          </Stack>
        </Container>
      </Box>

      <Box py={isMobile ? 64 : 88} bg={isDark ? theme.colors.dark[8] : '#ffffff'}>
        <Container size="1100" px={isMobile ? 'md' : 'xl'}>
          <Stack gap="xl">
            <Stack gap="sm" align="center" style={{ textAlign: 'center' }}>
              <Title order={2} c={isDark ? 'white' : '#111827'} style={{ fontSize: isMobile ? '1.9rem' : '2.6rem' }}>
                Come funziona
              </Title>
              <Text c={isDark ? theme.colors.gray[4] : '#4b5563'} maw={680}>
                Un flusso semplice: importi, capisci, poi decidi con piu controllo.
              </Text>
            </Stack>

            <Grid gutter="lg">
              {HOW_IT_WORKS.map(({ step, title, description, icon: Icon }) => (
                <Grid.Col key={title} span={{ base: 12, md: 4 }}>
                  <Card withBorder radius="xl" padding="xl" h="100%" bg={isDark ? theme.colors.dark[7] : '#ffffff'}>
                    <Stack gap="lg" h="100%">
                      <Group justify="space-between" align="flex-start">
                        <ThemeIcon color="teal" variant="light" radius="xl" size="xl">
                          <Icon size={18} />
                        </ThemeIcon>
                        <Text fw={800} size="sm" c={isDark ? theme.colors.teal[3] : emeraldDark}>
                          STEP {step}
                        </Text>
                      </Group>
                      <div>
                        <Title order={3} size="h4" mb="sm">{title}</Title>
                        <Text c={isDark ? theme.colors.gray[4] : '#4b5563'} style={{ lineHeight: 1.7 }}>
                          {description}
                        </Text>
                      </div>
                    </Stack>
                  </Card>
                </Grid.Col>
              ))}
            </Grid>
          </Stack>
        </Container>
      </Box>

      <Box py={isMobile ? 64 : 88} bg={softBackground}>
        <Container size="1100" px={isMobile ? 'md' : 'xl'}>
          <Stack gap="xl">
            <Stack gap="sm" align="center" style={{ textAlign: 'center' }}>
              <Title order={2} c={isDark ? 'white' : '#111827'} style={{ fontSize: isMobile ? '1.9rem' : '2.6rem' }}>
                Cosa ottieni davvero
              </Title>
              <Text c={isDark ? theme.colors.gray[4] : '#4b5563'} maw={680}>
                Non una dashboard in piu, ma un modo piu chiaro di leggere i tuoi soldi.
              </Text>
            </Stack>

            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
              {BENEFITS.map(({ title, description, icon: Icon }) => (
                <Card key={title} withBorder radius="xl" padding="xl" bg={isDark ? theme.colors.dark[6] : '#ffffff'}>
                  <Stack gap="md">
                    <Group gap="sm">
                      <ThemeIcon color="teal" variant="light" radius="xl" size="lg">
                        <Icon size={18} />
                      </ThemeIcon>
                      <Title order={3} size="h4">{title}</Title>
                    </Group>
                    <Text c={isDark ? theme.colors.gray[4] : '#4b5563'} style={{ lineHeight: 1.7 }}>
                      {description}
                    </Text>
                  </Stack>
                </Card>
              ))}
            </SimpleGrid>
          </Stack>
        </Container>
      </Box>

      <Box py={isMobile ? 64 : 88} bg={isDark ? theme.colors.dark[8] : '#ffffff'}>
        <Container size="920" px={isMobile ? 'md' : 'xl'}>
          <Stack gap="xl" align="center" style={{ textAlign: 'center' }}>
            <Card
              withBorder
              radius="xl"
              padding={isMobile ? 'xl' : '2rem'}
              w="100%"
              bg={isDark ? theme.colors.dark[7] : '#ffffff'}
            >
              <Stack gap="lg" align="center">
                <ThemeIcon color="teal" variant="light" radius="xl" size="xl">
                  <IconMessageCircle2 size={18} />
                </ThemeIcon>
                <Title order={2} c={isDark ? 'white' : '#111827'} style={{ fontSize: isMobile ? '1.8rem' : '2.5rem' }}>
                  AI quando serve. Umano quando conta.
                </Title>
                <Text c={isDark ? theme.colors.gray[4] : '#4b5563'} maw={680} style={{ lineHeight: 1.75 }}>
                  L'intelligenza artificiale analizza i dati.
                  Le persone ti aiutano a capire davvero.
                </Text>
              </Stack>
            </Card>

            <Card
              withBorder
              radius="xl"
              padding={isMobile ? 'xl' : '2rem'}
              w="100%"
              bg={isDark ? theme.colors.dark[7] : '#ffffff'}
            >
              <Stack gap="md" align="center">
                <Text fw={800} size="sm" c={isDark ? theme.colors.teal[3] : emeraldDark}>
                  LE PERSONE COME TE
                </Text>
                <Title order={2} c={isDark ? 'white' : '#111827'} style={{ fontSize: isMobile ? '1.8rem' : '2.4rem' }}>
                  Per la prima volta ho capito davvero cosa stavo facendo con i miei investimenti.
                </Title>
                <Text c={isDark ? theme.colors.gray[5] : '#6b7280'}>
                  Testimonial placeholder, pronto per review reali o case study.
                </Text>
              </Stack>
            </Card>
          </Stack>
        </Container>
      </Box>

      <Box
        py={isMobile ? 64 : 88}
        style={{
          background: isDark ? theme.colors.dark[7] : 'linear-gradient(180deg, #f0fdf4 0%, #ffffff 100%)',
          borderTop: isDark ? `1px solid ${theme.colors.dark[5]}` : '1px solid #e5e7eb',
        }}
      >
        <Container size="920" px={isMobile ? 'md' : 'xl'}>
          <Stack gap="lg" align="center" style={{ textAlign: 'center' }}>
            <Title order={2} c={isDark ? 'white' : '#111827'} style={{ fontSize: isMobile ? '2rem' : '2.8rem' }}>
              Inizia a capire i tuoi soldi
            </Title>
            <Text c={isDark ? theme.colors.gray[4] : '#4b5563'} maw={680} style={{ lineHeight: 1.7 }}>
              Parti dall'Instant Analyzer, ottieni un primo referto e poi approfondisci con Doctor, Dashboard e supporto umano.
            </Text>
            <Group gap="sm" wrap="wrap" justify="center">
              <Button
                component={Link}
                to="/instant-analyzer"
                color="teal"
                size="lg"
                radius="xl"
                rightSection={<IconArrowRight size={18} />}
              >
                Prova gratis
              </Button>
              <Button component={Link} to="/dashboard" variant="default" size="lg" radius="xl">
                Apri la piattaforma
              </Button>
            </Group>
          </Stack>
        </Container>
      </Box>
    </Box>
  );
}
