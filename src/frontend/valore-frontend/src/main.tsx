import React from 'react';
import ReactDOM from 'react-dom/client';
import { Drawer, MantineProvider, Modal, NumberInput, createTheme } from '@mantine/core';
import { ClerkProvider } from '@clerk/clerk-react';
import { ClerkTokenBridge } from './components/ClerkTokenBridge';
import App from './App.tsx';

// Importa gli stili obbligatori di Mantine
import '@mantine/core/styles.css';

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;
const theme = createTheme({
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
          color: theme.colors[theme.primaryColor][7],
          border: `1px solid ${theme.colors[theme.primaryColor][3]}`,
          backgroundColor: theme.white,
          '&:hover': {
            backgroundColor: theme.colors[theme.primaryColor][0],
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
          color: theme.colors[theme.primaryColor][7],
          border: `1px solid ${theme.colors[theme.primaryColor][3]}`,
          backgroundColor: theme.white,
          '&:hover': {
            backgroundColor: theme.colors[theme.primaryColor][0],
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
        <MantineProvider theme={theme}>
          <App />
        </MantineProvider>
      </ClerkProvider>
    );
  }

  return (
    <MantineProvider theme={theme}>
      <App />
    </MantineProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
