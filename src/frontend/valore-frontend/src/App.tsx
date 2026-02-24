import { useState } from 'react';
import {
  AppShell,
  Burger,
  Group,
  ActionIcon,
  Button,
  NavLink,
  Container,
  useMantineColorScheme,
  Title,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
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
import { PortfolioPage } from './pages/Portfolio.page.tsx';
import { DashboardPage } from './pages/Dashboard.page.tsx';
import { SettingsPage } from './pages/Settings.page.tsx';

function App() {
  const [opened, { toggle }] = useDisclosure();
  const [navbarExpanded, setNavbarExpanded] = useState(true);
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const handleGlobalRefresh = () => {
    window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard'));
  };

  return (
    <BrowserRouter>
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
              <Title order={3}>Valore365</Title>
            </Group>
            <Group>
              <ActionIcon onClick={toggleColorScheme} variant="default" size="lg" aria-label="Toggle color scheme">
                {colorScheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
              </ActionIcon>
              <Button leftSection={<IconRefresh size={16} />} variant="default" onClick={handleGlobalRefresh}>
                Aggiorna
              </Button>
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
          />
          <NavLink
              component={Link}
              to="/portfolio"
              label={navbarExpanded ? 'Portfolio' : undefined}
              leftSection={<IconBriefcase size={16} />}
              aria-label="Portfolio"
          />
          <NavLink
              component={Link}
              to="/settings"
              label={navbarExpanded ? 'Settings' : undefined}
              leftSection={<IconSettings size={16} />}
              aria-label="Settings"
          />
        </AppShell.Navbar>

        <AppShell.Main>
          <Container fluid>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </Container>
        </AppShell.Main>
      </AppShell>
    </BrowserRouter>
  );
}

export default App;
