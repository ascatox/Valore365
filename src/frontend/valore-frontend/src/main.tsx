import React, { useMemo } from 'react';
import ReactDOM from 'react-dom/client';
import { Drawer, MantineProvider, Modal, NumberInput, createTheme, type MantineColorsTuple } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ClerkProvider } from '@clerk/clerk-react';
import { ClerkTokenBridge } from './components/ClerkTokenBridge';
import App from './App.tsx';
import { initTextScale } from './textScale';
import { initColorTheme, useActiveColorTheme, type ColorTheme } from './colorTheme';

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

const IS_TOUCH_DEVICE = typeof window !== 'undefined'
  && window.matchMedia?.('(hover: none) and (pointer: coarse)').matches === true;

// Panels close with a "Chiudi" text button instead of an X icon.
const CLOSE_BUTTON_PROPS = { icon: <span>Chiudi</span>, 'aria-label': 'Chiudi' };
const CLOSE_TEXT_STYLES = {
  width: 'auto',
  minWidth: 'auto',
  height: 'auto',
  minHeight: '2.25rem',
  paddingInline: 10,
  borderRadius: 8,
  fontSize: '0.9375rem',
  fontWeight: 600,
  color: 'var(--mantine-primary-color-filled)',
  backgroundColor: 'transparent',
  border: 'none',
};

// The colour theme (colorTheme.ts; petrol by default) replaces two Mantine
// tuples: teal, which the app already uses as its brand colour, so every
// `color="teal"` and `theme.colors.teal[n]` follows it, and dark, the
// dark-mode neutrals, slightly tinted instead of Mantine's flat grey.
const buildTheme = (colorTheme: ColorTheme) => createTheme({
  primaryColor: 'teal',
  colors: {
    teal: colorTheme.primary,
    green: gain,
    red: loss,
    orange: attention,
    dark: colorTheme.dark,
  },
  // Radius by role: 8 for inputs, buttons and chips, 14 for cards, 20 for sheets.
  radius: { xs: '4px', sm: '8px', md: '14px', lg: '20px', xl: '28px' },
  fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
  headings: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
  },
  components: {
    NumberInput: NumberInput.extend({
      defaultProps: {
        thousandSeparator: '.',
        decimalSeparator: ',',
        // The default "numeric" keypad on iOS has no decimal separator.
        inputMode: 'decimal',
        // The up/down steppers are too small to tap; touch users type the value.
        hideControls: IS_TOUCH_DEVICE,
      },
    }),
    Modal: Modal.extend({
      defaultProps: { closeButtonProps: CLOSE_BUTTON_PROPS },
      styles: (theme) => ({
        title: {
          color: theme.colors[theme.primaryColor][6],
          fontWeight: 700,
        },
        close: CLOSE_TEXT_STYLES,
      }),
    }),
    Drawer: Drawer.extend({
      defaultProps: { closeButtonProps: CLOSE_BUTTON_PROPS },
      styles: (theme) => ({
        title: {
          color: theme.colors[theme.primaryColor][6],
          fontWeight: 700,
        },
        close: CLOSE_TEXT_STYLES,
      }),
    }),
  },
});

function Root() {
  // A new theme object only swaps Mantine's CSS variables: nothing remounts.
  const colorTheme = useActiveColorTheme();
  const theme = useMemo(() => buildTheme(colorTheme), [colorTheme]);

  if (clerkPubKey) {
    return (
      <ClerkProvider publishableKey={clerkPubKey}>
        <ClerkTokenBridge />
        <QueryClientProvider client={queryClient}>
          <MantineProvider theme={theme} defaultColorScheme="auto">
            <App />
          </MantineProvider>
        </QueryClientProvider>
      </ClerkProvider>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <MantineProvider theme={theme} defaultColorScheme="auto">
        <App />
      </MantineProvider>
    </QueryClientProvider>
  );
}

// Before the first render, so the page doesn't reflow once it's on screen.
initTextScale();
initColorTheme();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
