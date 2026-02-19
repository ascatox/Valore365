import {
  AppShell,
  Burger,
  Group,
  Switch,
  ActionIcon,
  Button,
  NavLink,
  Container,
  useMantineColorScheme,
  Title,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Sun, Moon, RefreshCw, LayoutDashboard, Briefcase, Settings } from 'lucide-react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { PortfolioPage } from './pages/Portfolio.page';
import { DashboardPage } from './pages/Dashboard.page';
import { SettingsPage } from './pages/Settings.page';

function App() {
  const [opened, { toggle }] = useDisclosure();
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();

  return (
    <BrowserRouter>
      <AppShell
        header={{ height: 60 }}
        navbar={{ width: 250, breakpoint: 'sm', collapsed: { mobile: !opened } }}
        padding="md"
      >
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between">
            <Group>
              <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
              <Title order={3}>Valore365</Title>
            </Group>
            <Group>
              <Switch label="Privacy Mode" offLabel="OFF" onLabel="ON" />
              <ActionIcon onClick={toggleColorScheme} variant="default" size="lg" aria-label="Toggle color scheme">
                {colorScheme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
              </ActionIcon>
              <Button leftSection={<RefreshCw size={16} />} variant="default">
                Aggiorna
              </Button>
            </Group>
          </Group>
        </AppShell.Header>

        <AppShell.Navbar p="md">
          <NavLink
              component={Link}
              to="/"
              label="Dashboard"
              leftSection={<LayoutDashboard size={16} />}
          />
          <NavLink
              component={Link}
              to="/portfolio"
              label="Portfolio"
              leftSection={<Briefcase size={16} />}
          />
          <NavLink
              component={Link}
              to="/settings"
              label="Settings"
              leftSection={<Settings size={16} />}
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
