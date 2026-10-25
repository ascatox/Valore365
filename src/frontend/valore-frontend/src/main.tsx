import React from 'react';
import ReactDOM from 'react-dom/client';
import { Drawer, MantineProvider, Modal, NumberInput, createTheme, type MantineColorsTuple } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ClerkProvider } from '@clerk/clerk-react';
import { ClerkTokenBridge } from './components/ClerkTokenBridge';
import App from './App.tsx';

// Importa gli stili obbligatori di Mantine
import '@mantine/core/styles.css';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;

// Brand petrol: replaces Mantine's teal, which the app already uses as its
// brand colour, so every `color="teal"` and `theme.colors.teal[n]` follows it.
// Shade 6 is the #0f766e used across the mobile components.
const petrol: MantineColorsTuple = [
  '#e7f4f2', '#cde8e4', '#9dd1c9', '#6bb8ad', '#3e9f93',
  '#1f877b', '#0f766e', '#0e6c65', '#0d625c', '#0b4a46',
];

// Gain, loss and attention. Shade 6 is the light-mode text/fill and shade 4
// the dark-mode text, so both keep readable contrast on their background.
const gain: MantineColorsTuple = [
  '#eaf7ee', '#d3efdb', '#a7dfb8', '#86d9a0', '#4ade80',
  '#22a352', '#15803d', '#146c35', '#125a2d', '#0f4524',
];
const loss: MantineColorsTuple = [
  '#fdecea', '#fbd5d1', '#f6aba3', '#f68f86', '#f87171',
  '#e04f45', '#b42318', '#a01f15', '#8a1b12', '#6e150e',
];
const attention: MantineColorsTuple = [
  '#fdf3e7', '#fbe3c4', '#f6c78b', '#f2b065', '#f0a04b',
  '#dd7d1c', '#c2620a', '#a85409', '#8f4708', '#6f3706',
];

// Dark-mode neutrals with a slight petrol tint, replacing Mantine's flat grey.
// dark[7] is the page background, dark[6] cards and inputs, dark[4] borders.
const petrolDark: MantineColorsTuple = [
  '#d3dcda', '#aab6b4', '#7c8987', '#55625f', '#2b3836',
  '#1b2726', '#151f1e', '#0e1514', '#0b1110', '#070c0b',
];

const theme = createTheme({
  primaryColor: 'teal',
  colors: {
    teal: petrol,
    green: gain,
    red: loss,
    orange: attention,
    dark: petrolDark,
  },
  fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
  headings: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
  },
  components: {
    NumberInput: NumberInput.extend({
      defaultProps: {
        thousandSeparator: '.',
        decimalSeparator: ',',
      },
    }),
    Modal: Modal.extend({
      styles: (theme) => ({
        title: {
          color: theme.colors[theme.primaryColor][6],
          fontWeight: 700,
        },
        close: {
          color: 'var(--mantine-color-text)',
          border: '1px solid var(--mantine-color-default-border)',
          backgroundColor: 'var(--mantine-color-body)',
          '&:hover': {
            backgroundColor: 'var(--mantine-color-default-hover)',
          },
        },
      }),
    }),
    Drawer: Drawer.extend({
      styles: (theme) => ({
        title: {
          color: theme.colors[theme.primaryColor][6],
          fontWeight: 700,
        },
        close: {
          color: 'var(--mantine-color-text)',
          border: '1px solid var(--mantine-color-default-border)',
          backgroundColor: 'var(--mantine-color-body)',
          '&:hover': {
            backgroundColor: 'var(--mantine-color-default-hover)',
          },
        },
      }),
    }),
  },
});

function Root() {
  if (clerkPubKey) {
    return (
      <ClerkProvider publishableKey={clerkPubKey}>
        <ClerkTokenBridge />
        <QueryClientProvider client={queryClient}>
          <MantineProvider theme={theme} defaultColorScheme="light">
            <App />
          </MantineProvider>
        </QueryClientProvider>
      </ClerkProvider>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <MantineProvider theme={theme} defaultColorScheme="light">
        <App />
      </MantineProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
