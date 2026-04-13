import { Suspense, lazy, useState, useEffect, useRef, useCallback } from 'react';
import {
  AppShell,
  Badge,
  Box,
  Burger,
  Group,
  ActionIcon,
  NavLink,
  Container,
  Transition,
  Tooltip,
  useMantineColorScheme,
} from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import { usePullToRefresh } from './hooks/usePullToRefresh';
import {
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
  IconShieldLock,
  IconDeviceMobile,
  IconInfoCircle,
  IconSparkles,
} from '@tabler/icons-react';
import { BrowserRouter, Routes, Route, Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { UserButton } from '@clerk/clerk-react';
import { AuthGuard } from './components/AuthGuard';
import { UpdatePrompt } from './pwa/UpdatePrompt';
import { BrandMark } from './components/BrandMark';
import { STORAGE_KEYS } from './components/dashboard/constants';
import { getAdminPortfolios, getAdminUsageSummary } from './services/api';

const InstantPortfolioAnalyzerPage = lazy(() => import('./pages/InstantPortfolioAnalyzerPage.tsx').then((module) => ({ default: module.InstantPortfolioAnalyzerPage })));
const LandingPage = lazy(() => import('./pages/LandingPage.tsx').then((module) => ({ default: module.LandingPage })));
const AdminPage = lazy(() => import('./pages/Admin.page.tsx').then((module) => ({ default: module.AdminPage })));
const DoctorPage = lazy(() => import('./pages/Doctor.page.tsx').then((module) => ({ default: module.DoctorPage })));
const FirePage = lazy(() => import('./pages/Fire.page.tsx').then((module) => ({ default: module.FirePage })));
const PortfolioPage = lazy(() => import('./pages/Portfolio.page.tsx').then((module) => ({ default: module.PortfolioPage })));
const DashboardPage = lazy(() => import('./pages/Dashboard.page.tsx').then((module) => ({ default: module.DashboardPage })));
const SettingsPage = lazy(() => import('./pages/Settings.page.tsx').then((module) => ({ default: module.SettingsPage })));
const AboutPage = lazy(() => import('./pages/About.page.tsx').then((module) => ({ default: module.AboutPage })));
const CreatorPage = lazy(() => import('./pages/Creator.page.tsx').then((module) => ({ default: module.CreatorPage })));

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
          <Route path="/" element={<LandingPage />} />
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
  const location = useLocation();
  const navigate = useNavigate();
  const mainRef = useRef<HTMLElement | null>(null);
  const [opened, { toggle, close }] = useDisclosure();
  const [navbarExpanded, setNavbarExpanded] = useState(true);
  const { colorScheme } = useMantineColorScheme();
  const isMobile = useMediaQuery('(max-width: 48em)');
  const isLandscape = useMediaQuery('(max-width: 48em) and (orientation: landscape)');
  const headerHeight = isLandscape ? 44 : 60;
  const [hasPortfolios, setHasPortfolios] = useState<boolean | null>(null);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);
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

  useEffect(() => {
    let active = true;

    const loadPortfolioAvailability = async () => {
      try {
        const portfolios = await getAdminPortfolios();
        if (active) {
          setHasPortfolios(portfolios.length > 0);
        }
      } catch {
        if (active) {
          setHasPortfolios(true);
        }
      }
    };

    const handlePortfoliosChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ count?: number }>).detail;
      if (typeof detail?.count === 'number') {
        setHasPortfolios(detail.count > 0);
        return;
      }
      void loadPortfolioAvailability();
    };

    void loadPortfolioAvailability();
    window.addEventListener('valore365:portfolios-changed', handlePortfoliosChanged as EventListener);
    return () => {
      active = false;
      window.removeEventListener('valore365:portfolios-changed', handlePortfoliosChanged as EventListener);
    };
  }, []);

  useEffect(() => {
    let active = true;

    const detectAdminAccess = async () => {
      try {
        await getAdminUsageSummary();
        if (active) {
          setIsAdmin(true);
        }
      } catch {
        if (active) {
          setIsAdmin(false);
        }
      }
    };

    void detectAdminAccess();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (
      hasPortfolios === false
      && location.pathname !== '/portfolio'
      && location.pathname !== '/creator'
      && location.pathname !== '/about'
      && !(isAdmin && location.pathname === '/admin')
    ) {
      navigate('/portfolio', { replace: true });
    }
  }, [hasPortfolios, isAdmin, location.pathname, navigate]);

  useEffect(() => {
    if (!isAdmin && location.pathname === '/admin') {
      navigate('/portfolio', { replace: true });
    }
  }, [isAdmin, location.pathname, navigate]);

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

  const { pulling, pullDistance, reached } = usePullToRefresh(mainRef, handleGlobalRefresh, { enabled: Boolean(isMobile) });
  const lockNonPortfolioNavigation = hasPortfolios === false;

  return (
      <AppShell
        header={{ height: headerHeight }}
        navbar={{ width: navbarExpanded ? 250 : 74, breakpoint: 'sm', collapsed: { mobile: !opened } }}
        padding={isLandscape ? 'xs' : 'md'}
        styles={{
          main: isMobile
            ? { paddingInline: 'var(--mantine-spacing-xs)' }
            : undefined,
        }}
      >
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between" wrap="nowrap">
            <Group wrap="nowrap">
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
            <Group gap="xs" wrap="nowrap">
              <Tooltip label={privacyMode ? 'Disattiva modalità privacy' : 'Attiva modalità privacy'} withArrow>
                <ActionIcon onClick={togglePrivacyMode} variant="default" size={isMobile ? 42 : 'lg'} aria-label="Modalità privacy" color={privacyMode ? 'blue' : undefined}>
                  {privacyMode ? <IconEyeOff size={isMobile ? 22 : 18} /> : <IconEye size={isMobile ? 22 : 18} />}
                </ActionIcon>
              </Tooltip>
              <Tooltip label={autoRefresh ? `Auto-refresh attivo (${countdownSec}s)` : 'Aggiorna'} withArrow>
                <ActionIcon
                  variant={autoRefresh ? 'filled' : 'default'}
                  color={autoRefresh ? 'blue' : undefined}
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
          <Tooltip label="Dashboard" position="right" withArrow disabled={navbarExpanded}>
            <NavLink
                component={Link}
                to="/dashboard"
                label={navbarExpanded ? 'Dashboard' : undefined}
                leftSection={<IconLayoutDashboard size={16} />}
                aria-label="Dashboard"
                disabled={lockNonPortfolioNavigation}
                onClick={close}
            />
          </Tooltip>
          <Tooltip label="Doctor" position="right" withArrow disabled={navbarExpanded}>
            <NavLink
                component={Link}
                to="/doctor"
                label={navbarExpanded ? 'Doctor' : undefined}
                leftSection={<IconHeartRateMonitor size={16} />}
                aria-label="Doctor"
                disabled={lockNonPortfolioNavigation}
                onClick={close}
            />
          </Tooltip>
          <Tooltip label="Portfolio" position="right" withArrow disabled={navbarExpanded}>
            <NavLink
                component={Link}
                to="/portfolio"
                label={navbarExpanded ? 'Portfolio' : undefined}
                leftSection={<IconBriefcase size={16} />}
                aria-label="Portfolio"
                onClick={close}
            />
          </Tooltip>
          <Tooltip label="Creator" position="right" withArrow disabled={navbarExpanded}>
            <NavLink
                component={Link}
                to="/creator"
                label={navbarExpanded ? 'Creator' : undefined}
                leftSection={<IconSparkles size={16} />}
                aria-label="Creator"
                onClick={close}
            />
          </Tooltip>
          <Tooltip label="FIRE" position="right" withArrow disabled={navbarExpanded}>
            <NavLink
                component={Link}
                to="/fire"
                label={navbarExpanded ? 'FIRE' : undefined}
                leftSection={<IconFlame size={16} />}
                aria-label="FIRE"
                disabled={lockNonPortfolioNavigation}
                onClick={close}
            />
          </Tooltip>
          <Tooltip label="Impostazioni" position="right" withArrow disabled={navbarExpanded}>
            <NavLink
                component={Link}
                to="/settings"
                label={navbarExpanded ? 'Impostazioni' : undefined}
                leftSection={<IconSettings size={16} />}
                aria-label="Impostazioni"
                disabled={lockNonPortfolioNavigation}
                onClick={close}
            />
          </Tooltip>
          <Tooltip label="About" position="right" withArrow disabled={navbarExpanded}>
            <NavLink
                component={Link}
                to="/about"
                label={navbarExpanded ? 'About' : undefined}
                leftSection={<IconInfoCircle size={16} />}
                aria-label="About"
                onClick={close}
            />
          </Tooltip>
          {isAdmin && (
            <Tooltip label="Admin" position="right" withArrow disabled={navbarExpanded}>
              <NavLink
                  component={Link}
                  to="/admin"
                  label={navbarExpanded ? 'Admin' : undefined}
                  leftSection={<IconShieldLock size={16} />}
                  aria-label="Admin"
                  onClick={close}
              />
            </Tooltip>
          )}
          <Box style={{ marginTop: 'auto', paddingTop: 16 }}>
            <Tooltip label="Ottimizzata per mobile" position="right" withArrow disabled={navbarExpanded}>
              <Badge
                variant="light"
                color="teal"
                size={navbarExpanded ? 'md' : 'xs'}
                leftSection={<IconDeviceMobile size={14} />}
                fullWidth={navbarExpanded}
                style={!navbarExpanded ? { padding: 4, display: 'flex', justifyContent: 'center' } : undefined}
              >
                {navbarExpanded ? 'Mobile ready' : undefined}
              </Badge>
            </Tooltip>
          </Box>
        </AppShell.Navbar>

        <UpdatePrompt />
        <AppShell.Main ref={mainRef}>
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
          <Container fluid px={0} key={`privacy-${privacyMode}`}>
            <Routes>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/doctor" element={<DoctorPage />} />
              <Route path="/fire" element={<FirePage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/creator" element={<CreatorPage />} />
              <Route path="/about" element={<AboutPage />} />
              <Route path="/admin" element={<AdminPage />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </Container>
        </AppShell.Main>
      </AppShell>
  );
}

export default App;
