import { Suspense, lazy, useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';
import {
  AppShell,
  Badge,
  Box,
  Center,
  Loader,
  SimpleGrid,
  Stack,
  Text,
  UnstyledButton,
  Group,
  ActionIcon,
  Menu,
  NavLink,
  Container,
  Transition,
  Tooltip,
  useComputedColorScheme,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useIsMobile } from './hooks/useIsMobile';
import { useActiveColorTheme } from './colorTheme';
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
  IconDotsVertical,
  IconDots,
  IconPlus,
  IconArrowsExchange,
  IconFileImport,
  IconCoins,
  IconFolderPlus,
} from '@tabler/icons-react';
import { BrowserRouter, Routes, Route, Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { UserButton } from '@clerk/clerk-react';
import { AuthGuard } from './components/AuthGuard';
import { UpdatePrompt } from './pwa/UpdatePrompt';
import { BrandMark } from './components/BrandMark';
import { MobileBottomNav } from './components/mobile/MobileBottomNav';
import { BottomSheet } from './components/mobile/BottomSheet';
import { STORAGE_KEYS } from './components/dashboard/constants';
import { getAdminPortfolios, getAdminUsageSummary } from './services/api';
import { PortfolioScopeProvider, useOptionalPortfolioScope } from './scope/PortfolioScopeContext';
import { AGGREGATE_READ_ONLY_HINT } from './scope/aggregateLabels';

// Page chunks: each loader is shared by lazy() and the idle-time prefetch, so
// a prefetched chunk is the very module the route renders.
const pageLoaders = {
  instantAnalyzer: () => import('./pages/InstantPortfolioAnalyzerPage.tsx').then((module) => ({ default: module.InstantPortfolioAnalyzerPage })),
  landing: () => import('./pages/LandingPage.tsx').then((module) => ({ default: module.LandingPage })),
  admin: () => import('./pages/Admin.page.tsx').then((module) => ({ default: module.AdminPage })),
  doctor: () => import('./pages/Doctor.page.tsx').then((module) => ({ default: module.DoctorPage })),
  fire: () => import('./pages/Fire.page.tsx').then((module) => ({ default: module.FirePage })),
  portfolio: () => import('./pages/Portfolio.page.tsx').then((module) => ({ default: module.PortfolioPage })),
  dashboard: () => import('./pages/Dashboard.page.tsx').then((module) => ({ default: module.DashboardPage })),
  settings: () => import('./pages/Settings.page.tsx').then((module) => ({ default: module.SettingsPage })),
  about: () => import('./pages/About.page.tsx').then((module) => ({ default: module.AboutPage })),
  creator: () => import('./pages/Creator.page.tsx').then((module) => ({ default: module.CreatorPage })),
};

const InstantPortfolioAnalyzerPage = lazy(pageLoaders.instantAnalyzer);
const LandingPage = lazy(pageLoaders.landing);
const AdminPage = lazy(pageLoaders.admin);
const DoctorPage = lazy(pageLoaders.doctor);
const FirePage = lazy(pageLoaders.fire);
const PortfolioPage = lazy(pageLoaders.portfolio);
const DashboardPage = lazy(pageLoaders.dashboard);
const SettingsPage = lazy(pageLoaders.settings);
const AboutPage = lazy(pageLoaders.about);
const CreatorPage = lazy(pageLoaders.creator);

// Pages reachable from the app navigation, in the order they're prefetched
// (bottom-nav tabs first): the first visit to a tab then has no chunk to wait for.
const PREFETCHED_PAGES = [
  pageLoaders.dashboard,
  pageLoaders.portfolio,
  pageLoaders.doctor,
  pageLoaders.fire,
  pageLoaders.settings,
  pageLoaders.creator,
  pageLoaders.about,
];

function prefetchAppPages() {
  const run = () => {
    // One at a time, so the prefetch never competes with the current page.
    void PREFETCHED_PAGES.reduce<Promise<unknown>>(
      (chain, load) => chain.then(() => load().catch(() => undefined)),
      Promise.resolve(),
    );
  };
  const idle = (window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number }).requestIdleCallback;
  if (idle) {
    idle(run, { timeout: 3000 });
  } else {
    window.setTimeout(run, 1500);
  }
}

// Shown only while a page chunk loads for the first time; the app shell
// (header, bottom nav) stays mounted around it.
function PageFallback() {
  return (
    <Center py="xl" mih={160} aria-busy="true" aria-label="Caricamento pagina">
      <Loader size="sm" />
    </Center>
  );
}

const clerkEnabled = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

function App() {
  return (
    <BrowserRouter>
      <Suspense
        fallback={<PageFallback />}
      >
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/instant-analyzer" element={<InstantPortfolioAnalyzerPage />} />
          <Route
            path="/*"
            element={(
              <AuthGuard>
                <PortfolioScopeProvider>
                  <ProtectedApp />
                </PortfolioScopeProvider>
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
  const [navbarExpanded, setNavbarExpanded] = useState(true);
  const colorScheme = useComputedColorScheme('light');
  const isMobile = useIsMobile();
  const portfolioScope = useOptionalPortfolioScope();
  const isLandscape = useMediaQuery('(max-width: 48em) and (orientation: landscape)', undefined, { getInitialValueInEffect: false });
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

  // Load the other pages' chunks once the current one is up.
  useEffect(() => {
    prefetchAppPages();
  }, []);

  // A new page starts at the top: the window keeps the previous page's
  // offset otherwise, so the new page opened half-way down (or showed the end
  // of the old one while it grew). Layout effect: runs before the new page is
  // painted. Query-only changes (?azione=, ?tab=) keep the position.
  useLayoutEffect(() => {
    window.scrollTo(0, 0);
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [location.pathname]);

  // Dark browser chrome matches the page background of the colour theme.
  const darkPageBg = useActiveColorTheme().dark[7];
  useEffect(() => {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', colorScheme === 'dark' ? darkPageBg : '#ffffff');
    }
  }, [colorScheme, darkPageBg]);

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

  // Spins the mobile header refresh icon while the dashboard refresh runs.
  const [dashboardRefreshing, setDashboardRefreshing] = useState(false);
  useEffect(() => {
    const onState = (event: Event) => setDashboardRefreshing(Boolean((event as CustomEvent<boolean>).detail));
    window.addEventListener('valore365:refresh-state', onState);
    return () => window.removeEventListener('valore365:refresh-state', onState);
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

  // --- Mobile app navigation: one bottom bar on every page ---
  const [moreSheetOpened, setMoreSheetOpened] = useState(false);
  const [actionSheetOpened, setActionSheetOpened] = useState(false);

  const mobileNavItems = [
    { value: '/dashboard', label: 'Home', icon: IconLayoutDashboard, disabled: lockNonPortfolioNavigation },
    { value: '/portfolio', label: 'Portfolio', icon: IconBriefcase },
    { value: '/doctor', label: 'Doctor', icon: IconHeartRateMonitor, disabled: lockNonPortfolioNavigation },
    { value: 'altro', label: 'Altro', icon: IconDots },
  ];
  const activeMobileNav = mobileNavItems.some((item) => item.value === location.pathname)
    ? location.pathname
    : 'altro';

  const moreItems = [
    { to: '/fire', label: 'FIRE', icon: IconFlame, disabled: lockNonPortfolioNavigation },
    { to: '/creator', label: 'Creator', icon: IconSparkles },
    { to: '/settings', label: 'Impostazioni', icon: IconSettings, disabled: lockNonPortfolioNavigation },
    { to: '/about', label: 'About', icon: IconInfoCircle },
    ...(isAdmin ? [{ to: '/admin', label: 'Admin', icon: IconShieldLock }] : []),
  ];

  // The "+" sheet hands its action to the Portfolio page through ?azione=,
  // which opens the matching drawer or modal there.
  // The aggregate view is read-only: the actions that write to one portfolio
  // are off there, with the reason in place of their description.
  const aggregateReadOnly = portfolioScope?.isAggregate ?? false;
  const quickActions = [
    { action: 'nuova-transazione', label: 'Nuova transazione', description: aggregateReadOnly ? AGGREGATE_READ_ONLY_HINT : 'Acquisto, vendita, dividendo o movimento di cassa', icon: IconArrowsExchange, disabled: lockNonPortfolioNavigation || aggregateReadOnly },
    { action: 'importa', label: 'Importa movimenti', description: aggregateReadOnly ? AGGREGATE_READ_ONLY_HINT : 'Da file CSV o XLSX del broker', icon: IconFileImport, disabled: aggregateReadOnly },
    { action: 'nuova-regola-pac', label: 'Nuova regola PAC', description: aggregateReadOnly ? AGGREGATE_READ_ONLY_HINT : 'Versamento ricorrente su un asset', icon: IconCoins, disabled: lockNonPortfolioNavigation || aggregateReadOnly },
    { action: 'nuovo-portafoglio', label: 'Nuovo portafoglio', description: 'Con valuta base e liquidità dedicate', icon: IconFolderPlus },
  ];

  const handleMobileNavChange = (value: string) => {
    if (value === 'altro') {
      setMoreSheetOpened(true);
      return;
    }
    navigate(value);
  };

  return (
      <AppShell
        header={{ height: `calc(${headerHeight}px + var(--safe-area-top))` }}
        navbar={{ width: navbarExpanded ? 250 : 74, breakpoint: 'sm', collapsed: { mobile: true } }}
        padding={isLandscape ? 'xs' : 'md'}
        styles={{
          header: {
            paddingTop: 'var(--safe-area-top)',
            paddingLeft: 'var(--safe-area-left)',
            paddingRight: 'var(--safe-area-right)',
          },
          main: isMobile
            ? { paddingInline: 'var(--mantine-spacing-xs)', paddingBottom: 'var(--v365-mobile-nav-space)' }
            : undefined,
        }}
      >
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between" wrap="nowrap">
            <Group wrap="nowrap">
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
              {isMobile && (
                <ActionIcon
                  onClick={handleGlobalRefresh}
                  variant="subtle"
                  color="gray"
                  size={42}
                  aria-label={dashboardRefreshing ? 'Aggiornamento in corso' : 'Aggiorna ora'}
                >
                  <IconRefresh
                    size={22}
                    style={dashboardRefreshing ? { animation: 'spin 1s linear infinite' } : undefined}
                  />
                </ActionIcon>
              )}
            </Group>
            <Group gap="xs" wrap="nowrap">
              <Tooltip label={privacyMode ? 'Disattiva modalità privacy' : 'Attiva modalità privacy'} withArrow>
                <ActionIcon onClick={togglePrivacyMode} variant="default" size={isMobile ? 42 : 'lg'} aria-label="Modalità privacy" color={privacyMode ? 'teal' : undefined}>
                  {privacyMode ? <IconEyeOff size={isMobile ? 22 : 18} /> : <IconEye size={isMobile ? 22 : 18} />}
                </ActionIcon>
              </Tooltip>
              {isMobile ? (
                // The explicit refresh sits in the header next to
                // pull-to-refresh; the 60s auto-refresh lives in a menu.
                <Menu position="bottom-end" withinPortal>
                  <Menu.Target>
                    <ActionIcon
                      variant={autoRefresh ? 'filled' : 'default'}
                      color={autoRefresh ? 'teal' : undefined}
                      size={42}
                      aria-label="Altre azioni"
                    >
                      <IconDotsVertical size={22} />
                    </ActionIcon>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item
                      leftSection={autoRefresh ? <IconPlayerStop size={16} /> : <IconPlayerPlay size={16} />}
                      onClick={toggleAutoRefresh}
                    >
                      {autoRefresh ? `Ferma auto-refresh (${countdownSec}s)` : 'Auto-refresh ogni 60s'}
                    </Menu.Item>
                  </Menu.Dropdown>
                </Menu>
              ) : (
              <>
              <Tooltip label={autoRefresh ? `Auto-refresh attivo (${countdownSec}s)` : 'Aggiorna'} withArrow>
                <ActionIcon
                  variant={autoRefresh ? 'filled' : 'default'}
                  color={autoRefresh ? 'teal' : undefined}
                  size="lg"
                  onClick={handleGlobalRefresh}
                  onDoubleClick={toggleAutoRefresh}
                  aria-label="Aggiorna"
                >
                  <IconRefresh
                    size={18}
                    style={autoRefresh ? { animation: 'spin 2s linear infinite' } : undefined}
                  />
                </ActionIcon>
              </Tooltip>
              <Tooltip label={autoRefresh ? 'Disattiva auto-refresh' : 'Attiva auto-refresh (60s)'} withArrow>
                <ActionIcon
                  variant={autoRefresh ? 'filled' : 'default'}
                  color={autoRefresh ? 'teal' : undefined}
                  size="lg"
                  onClick={toggleAutoRefresh}
                  aria-label="Auto-refresh"
                >
                  {autoRefresh
                    ? <IconPlayerStop size={18} />
                    : <IconPlayerPlay size={18} />}
                </ActionIcon>
              </Tooltip>
              </>
              )}
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
            />
          </Tooltip>
          <Tooltip label="Portfolio" position="right" withArrow disabled={navbarExpanded}>
            <NavLink
                component={Link}
                to="/portfolio"
                label={navbarExpanded ? 'Portfolio' : undefined}
                leftSection={<IconBriefcase size={16} />}
                aria-label="Portfolio"
            />
          </Tooltip>
          <Tooltip label="Creator" position="right" withArrow disabled={navbarExpanded}>
            <NavLink
                component={Link}
                to="/creator"
                label={navbarExpanded ? 'Creator' : undefined}
                leftSection={<IconSparkles size={16} />}
                aria-label="Creator"
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
            />
          </Tooltip>
          <Tooltip label="About" position="right" withArrow disabled={navbarExpanded}>
            <NavLink
                component={Link}
                to="/about"
                label={navbarExpanded ? 'About' : undefined}
                leftSection={<IconInfoCircle size={16} />}
                aria-label="About"
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
                    color: reached ? 'var(--mantine-primary-color-filled)' : 'var(--mantine-color-dimmed)',
                  }}
                />
              </div>
            )}
          </Transition>
          <Container fluid px={0} key={`privacy-${privacyMode}`}>
            {/* Inner boundary: a page chunk still loading suspends only the
                content area, never the AppShell around it. Navigations run in
                a transition (React Router v7 default), so an already-shown
                page stays on screen until the next one is ready. */}
            <Suspense fallback={<PageFallback />}>
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
            </Suspense>
          </Container>
        </AppShell.Main>

        {isMobile && (
          <>
            <MobileBottomNav
              items={mobileNavItems}
              value={activeMobileNav}
              onChange={handleMobileNavChange}
              centerAction={{ label: 'Azioni rapide', icon: IconPlus, onClick: () => setActionSheetOpened(true) }}
            />

            <BottomSheet
              opened={actionSheetOpened}
              onClose={() => setActionSheetOpened(false)}
              title="Azioni rapide"
            >
              <Stack gap={4}>
                {quickActions.map((item) => {
                  const Icon = item.icon;
                  return (
                    <UnstyledButton
                      key={item.action}
                      disabled={item.disabled}
                      onClick={() => {
                        setActionSheetOpened(false);
                        navigate(`/portfolio?azione=${item.action}`);
                      }}
                      style={{ padding: '10px 4px', borderRadius: 12, opacity: item.disabled ? 0.45 : 1 }}
                    >
                      <Group gap="sm" wrap="nowrap">
                        <Box
                          style={{
                            width: 40,
                            height: 40,
                            flexShrink: 0,
                            borderRadius: 12,
                            display: 'grid',
                            placeItems: 'center',
                            background: 'var(--mantine-primary-color-light)',
                            color: 'var(--mantine-primary-color-light-color)',
                          }}
                        >
                          <Icon size={20} />
                        </Box>
                        <Box style={{ minWidth: 0 }}>
                          <Text fw={700} size="sm">{item.label}</Text>
                          <Text size="xs" c="dimmed">{item.description}</Text>
                        </Box>
                      </Group>
                    </UnstyledButton>
                  );
                })}
              </Stack>
            </BottomSheet>

            <BottomSheet
              opened={moreSheetOpened}
              onClose={() => setMoreSheetOpened(false)}
              title="Altro"
            >
              <SimpleGrid cols={3} spacing="sm">
                {moreItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = location.pathname === item.to;
                  return (
                    <UnstyledButton
                      key={item.to}
                      disabled={item.disabled}
                      onClick={() => {
                        setMoreSheetOpened(false);
                        navigate(item.to);
                      }}
                      style={{
                        padding: '14px 6px',
                        borderRadius: 14,
                        textAlign: 'center',
                        border: `1px solid ${isActive ? 'var(--mantine-primary-color-filled)' : 'var(--mantine-color-default-border)'}`,
                        opacity: item.disabled ? 0.45 : 1,
                      }}
                    >
                      <Icon size={22} style={{ display: 'block', margin: '0 auto 6px', color: 'var(--mantine-primary-color-filled)' }} />
                      <Text size="sm" fw={600}>{item.label}</Text>
                    </UnstyledButton>
                  );
                })}
              </SimpleGrid>
            </BottomSheet>
          </>
        )}
      </AppShell>
  );
}

export default App;
