import { Suspense, lazy, useState, useEffect } from 'react';
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
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
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
import { BrandMark } from './components/BrandMark';

const InstantPortfolioAnalyzerPage = lazy(() => import('./pages/InstantPortfolioAnalyzerPage.tsx').then((module) => ({ default: module.InstantPortfolioAnalyzerPage })));
const PortfolioPage = lazy(() => import('./pages/Portfolio.page.tsx').then((module) => ({ default: module.PortfolioPage })));
const DashboardPage = lazy(() => import('./pages/Dashboard.page.tsx').then((module) => ({ default: module.DashboardPage })));
const SettingsPage = lazy(() => import('./pages/Settings.page.tsx').then((module) => ({ default: module.SettingsPage })));

const clerkEnabled = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

function App() {
  return (
    <BrowserRouter>
      <Suspense
        fallback={(
          <Box py="xl" ta="center" c="dimmed">
            Caricamento pagina...
          </Box>
        )}
      >
        <Routes>
          <Route path="/instant-analyzer" element={<InstantPortfolioAnalyzerPage />} />
          <Route
            path="/*"
            element={(
              <AuthGuard>
                <ProtectedApp />
              </AuthGuard>
            )}
          />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

function ProtectedApp() {
  const [opened, { toggle, close }] = useDisclosure();
  const [navbarExpanded, setNavbarExpanded] = useState(true);
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const isMobile = useMediaQuery('(max-width: 48em)');

  useEffect(() => {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', colorScheme === 'dark' ? '#242424' : '#ffffff');
    }
  }, [colorScheme]);

  const handleGlobalRefresh = () => {
    window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard'));
  };
  const { pulling, pullDistance, reached } = usePullToRefresh(handleGlobalRefresh);

  return (
      <AppShell
        header={{ height: 60 }}
        navbar={{ width: navbarExpanded ? 250 : 74, breakpoint: 'sm', collapsed: { mobile: !opened } }}
        padding="md"
      >
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between">
            <Group>
              <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="md" />
              <ActionIcon
                visibleFrom="sm"
                variant="default"
                size="lg"
                aria-label={navbarExpanded ? 'Comprimi menu laterale' : 'Espandi menu laterale'}
                onClick={() => setNavbarExpanded((v) => !v)}
              >
                {navbarExpanded ? <IconChevronsLeft size={18} /> : <IconChevronsRight size={18} />}
              </ActionIcon>
              <Box visibleFrom="sm">
                <BrandMark />
              </Box>
              <Box hiddenFrom="sm">
                <BrandMark compact />
              </Box>
            </Group>
            <Group>
              <ActionIcon onClick={toggleColorScheme} variant="default" size={isMobile ? 42 : 'lg'} aria-label="Cambia tema">
                {colorScheme === 'dark' ? <IconSun size={isMobile ? 22 : 18} /> : <IconMoon size={isMobile ? 22 : 18} />}
              </ActionIcon>
              <ActionIcon variant="default" size={42} onClick={handleGlobalRefresh} hiddenFrom="sm" aria-label="Aggiorna">
                <IconRefresh size={22} />
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
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </Container>
        </AppShell.Main>
      </AppShell>
  );
}

export default App;
