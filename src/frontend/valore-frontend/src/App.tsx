import { Suspense, lazy, useState } from 'react';
import {
  AppShell,
  Box,
  Burger,
  Group,
  ActionIcon,
  Button,
  NavLink,
  Container,
  Transition,
  useMantineColorScheme,
  Title,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { usePullToRefresh } from './hooks/usePullToRefresh';
import {
  IconSun,
  IconMoon,
  IconRefresh,
  IconLayoutDashboard,
  IconBriefcase,
  IconSettings,
  IconChevronsLeft,
  IconChevronsRight,
} from '@tabler/icons-react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { UserButton } from '@clerk/clerk-react';
import { AuthGuard } from './components/AuthGuard';

const PortfolioPage = lazy(() => import('./pages/Portfolio.page.tsx').then((module) => ({ default: module.PortfolioPage })));
const DashboardPage = lazy(() => import('./pages/Dashboard.page.tsx').then((module) => ({ default: module.DashboardPage })));
const SettingsPage = lazy(() => import('./pages/Settings.page.tsx').then((module) => ({ default: module.SettingsPage })));

const clerkEnabled = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

function App() {
  const [opened, { toggle, close }] = useDisclosure();
  const [navbarExpanded, setNavbarExpanded] = useState(true);
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const handleGlobalRefresh = () => {
    window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard'));
  };
  const { pulling, pullDistance, reached } = usePullToRefresh(handleGlobalRefresh);

  return (
    <BrowserRouter>
      <AuthGuard>
      <AppShell
        header={{ height: 60 }}
        navbar={{ width: navbarExpanded ? 250 : 74, breakpoint: 'sm', collapsed: { mobile: !opened } }}
        padding="md"
      >
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between">
            <Group>
              <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
              <ActionIcon
                visibleFrom="sm"
                variant="default"
                size="lg"
                aria-label={navbarExpanded ? 'Comprimi menu laterale' : 'Espandi menu laterale'}
                onClick={() => setNavbarExpanded((v) => !v)}
              >
                {navbarExpanded ? <IconChevronsLeft size={18} /> : <IconChevronsRight size={18} />}
              </ActionIcon>
              <Title order={3} visibleFrom="sm">Valore365</Title>
              <Title order={4} hiddenFrom="sm">Valore365</Title>
            </Group>
            <Group>
              <ActionIcon onClick={toggleColorScheme} variant="default" size="lg" aria-label="Cambia tema">
                {colorScheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
              </ActionIcon>
              <ActionIcon variant="default" size="lg" onClick={handleGlobalRefresh} hiddenFrom="sm" aria-label="Aggiorna">
                <IconRefresh size={18} />
              </ActionIcon>
              <Button leftSection={<IconRefresh size={16} />} variant="default" onClick={handleGlobalRefresh} visibleFrom="sm">
                Aggiorna
              </Button>
              {clerkEnabled && <UserButton afterSignOutUrl="/" />}
            </Group>
          </Group>
        </AppShell.Header>

        <AppShell.Navbar p="md">
          <NavLink
              component={Link}
              to="/"
              label={navbarExpanded ? 'Dashboard' : undefined}
              leftSection={<IconLayoutDashboard size={16} />}
              aria-label="Dashboard"
              onClick={close}
          />
          <NavLink
              component={Link}
              to="/portfolio"
              label={navbarExpanded ? 'Portfolio' : undefined}
              leftSection={<IconBriefcase size={16} />}
              aria-label="Portfolio"
              onClick={close}
          />
          <NavLink
              component={Link}
              to="/settings"
              label={navbarExpanded ? 'Impostazioni' : undefined}
              leftSection={<IconSettings size={16} />}
              aria-label="Impostazioni"
              onClick={close}
          />
        </AppShell.Navbar>

        <AppShell.Main>
          <Transition mounted={pulling} transition="slide-down" duration={150}>
            {(styles) => (
              <div
                style={{
                  ...styles,
                  display: 'flex',
                  justifyContent: 'center',
                  padding: 8,
                  overflow: 'hidden',
                  height: pullDistance * 0.4,
                }}
              >
                <IconRefresh
                  size={24}
                  style={{
                    transition: 'transform 0.2s',
                    transform: `rotate(${pullDistance * 3}deg)`,
                    opacity: reached ? 1 : 0.4,
                    color: reached ? 'var(--mantine-color-blue-6)' : 'var(--mantine-color-dimmed)',
                  }}
                />
              </div>
            )}
          </Transition>
          <Container fluid>
            <Suspense
              fallback={(
                <Box py="xl" ta="center" c="dimmed">
                  Caricamento pagina...
                </Box>
              )}
            >
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/portfolio" element={<PortfolioPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Routes>
            </Suspense>
          </Container>
        </AppShell.Main>
      </AppShell>
      </AuthGuard>
    </BrowserRouter>
  );
}

export default App;
