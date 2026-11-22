import React, { useMemo } from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ClerkProvider } from '@clerk/clerk-react';
import { ClerkTokenBridge } from './components/ClerkTokenBridge';
import App from './App.tsx';
import { initTextScale } from './textScale';
import { initColorTheme, useActiveColorTheme } from './colorTheme';
import { buildTheme } from './mantineTheme';

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
