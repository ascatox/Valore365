import { Suspense, lazy, useState, useEffect, useRef, useCallback } from 'react';
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
  Tooltip,
  useMantineColorScheme,
  Title,
} from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import { usePullToRefresh } from './hooks/usePullToRefresh';
import {
  IconSun,
  IconMoon,
  IconRefresh,
  IconPlayerPlay,
  IconPlayerStop,
  IconLayoutDashboard,
  IconBriefcase,
  IconFlame,
  IconHeartRateMonitor,
  IconSettings,
  IconChevronsLeft,
  IconChevronsRight,
  IconEye,
  IconEyeOff,
} from '@tabler/icons-react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { UserButton } from '@clerk/clerk-react';
import { AuthGuard } from './components/AuthGuard';
import { BrandMark } from './components/BrandMark';
import { STORAGE_KEYS } from './components/dashboard/constants';

const InstantPortfolioAnalyzerPage = lazy(() => import('./pages/InstantPortfolioAnalyzerPage.tsx').then((module) => ({ default: module.InstantPortfolioAnalyzerPage })));
const DoctorPage = lazy(() => import('./pages/Doctor.page.tsx').then((module) => ({ default: module.DoctorPage })));
const FirePage = lazy(() => import('./pages/Fire.page.tsx').then((module) => ({ default: module.FirePage })));
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
  const [privacyMode, setPrivacyMode] = useState(() =>
    window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled) === 'true',
  );

  const togglePrivacyMode = () => {
    const next = !privacyMode;
    setPrivacyMode(next);
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, String(next));
    window.dispatchEvent(new CustomEvent('valore365:privacy-changed', { detail: next }));
  };

  useEffect(() => {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', colorScheme === 'dark' ? '#242424' : '#ffffff');
    }
  }, [colorScheme]);

  const handleGlobalRefresh = useCallback(() => {
    window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard'));
  }, []);

  const AUTO_REFRESH_INTERVAL = 60_000;
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [countdown, setCountdown] = useState(AUTO_REFRESH_INTERVAL);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearTimers = useCallback(() => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
  }, []);

  const startAutoRefresh = useCallback(() => {
    clearTimers();
    setCountdown(AUTO_REFRESH_INTERVAL);
    intervalRef.current = setInterval(() => {
      handleGlobalRefresh();
      setCountdown(AUTO_REFRESH_INTERVAL);
    }, AUTO_REFRESH_INTERVAL);
    tickRef.current = setInterval(() => {
      setCountdown((c) => Math.max(0, c - 1000));
    }, 1000);
  }, [clearTimers, handleGlobalRefresh]);

  useEffect(() => {
    if (autoRefresh) {
      handleGlobalRefresh();
      startAutoRefresh();
    } else {
      clearTimers();
      setCountdown(AUTO_REFRESH_INTERVAL);
    }
    return clearTimers;
  }, [autoRefresh, startAutoRefresh, clearTimers, handleGlobalRefresh]);

  const toggleAutoRefresh = () => setAutoRefresh((v) => !v);
  const countdownSec = Math.ceil(countdown / 1000);

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
              <Tooltip label={privacyMode ? 'Disattiva modalità privacy' : 'Attiva modalità privacy'} withArrow>
                <ActionIcon onClick={togglePrivacyMode} variant="default" size={isMobile ? 42 : 'lg'} aria-label="Modalità privacy" color={privacyMode ? 'blue' : undefined}>
                  {privacyMode ? <IconEyeOff size={isMobile ? 22 : 18} /> : <IconEye size={isMobile ? 22 : 18} />}
                </ActionIcon>
              </Tooltip>
              <Box visibleFrom="sm">
                <Tooltip label={colorScheme === 'dark' ? 'Tema chiaro' : 'Tema scuro'} withArrow>
                  <ActionIcon onClick={toggleColorScheme} variant="default" size="lg" aria-label="Cambia tema">
                    {colorScheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
                  </ActionIcon>
                </Tooltip>
              </Box>
              <Tooltip label={autoRefresh ? `Auto-refresh attivo (${countdownSec}s)` : 'Aggiorna'} withArrow>
                <ActionIcon
                  variant={autoRefresh || isMobile ? 'filled' : 'default'}
                  color={autoRefresh ? 'blue' : isMobile ? 'teal' : undefined}
                  size={isMobile ? 42 : 'lg'}
                  onClick={handleGlobalRefresh}
                  onDoubleClick={toggleAutoRefresh}
                  aria-label="Aggiorna"
                >
                  <IconRefresh
                    size={isMobile ? 22 : 18}
                    style={autoRefresh ? { animation: 'spin 2s linear infinite' } : undefined}
                  />
                </ActionIcon>
              </Tooltip>
              <Tooltip label={autoRefresh ? 'Disattiva auto-refresh' : 'Attiva auto-refresh (60s)'} withArrow>
                <ActionIcon
                  variant={autoRefresh ? 'filled' : 'default'}
                  color={autoRefresh ? 'blue' : undefined}
                  size={isMobile ? 42 : 'lg'}
                  onClick={toggleAutoRefresh}
                  aria-label="Auto-refresh"
                >
                  {autoRefresh
                    ? <IconPlayerStop size={isMobile ? 22 : 18} />
                    : <IconPlayerPlay size={isMobile ? 22 : 18} />}
                </ActionIcon>
              </Tooltip>
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
              to="/doctor"
              label={navbarExpanded ? 'Doctor' : undefined}
              leftSection={<IconHeartRateMonitor size={16} />}
              aria-label="Doctor"
              onClick={close}
          />
          <NavLink
              component={Link}
              to="/fire"
              label={navbarExpanded ? 'FIRE' : undefined}
              leftSection={<IconFlame size={16} />}
              aria-label="FIRE"
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
          <Container fluid key={`privacy-${privacyMode}`}>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/doctor" element={<DoctorPage />} />
              <Route path="/fire" element={<FirePage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </Container>
        </AppShell.Main>
      </AppShell>
  );
}

export default App;
