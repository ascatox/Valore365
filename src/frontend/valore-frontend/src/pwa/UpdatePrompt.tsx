import { Notification, Button, Group } from '@mantine/core'
import { IconRefresh, IconCheck } from '@tabler/icons-react'
import { useServiceWorker } from './useServiceWorker'

/**
 * Floating prompt shown when a new version of the app is available,
 * or when the app is ready for offline use.
 */
export function UpdatePrompt() {
  const { needRefresh, offlineReady, updateServiceWorker, dismiss } =
    useServiceWorker()

  if (!needRefresh && !offlineReady) return null

  return (
    <Notification
      withCloseButton
      onClose={dismiss}
      icon={needRefresh ? <IconRefresh size={18} /> : <IconCheck size={18} />}
      color={needRefresh ? 'blue' : 'green'}
      title={
        needRefresh
          ? 'Nuova versione disponibile'
          : 'App pronta per uso offline'
      }
      style={{
        position: 'fixed',
        bottom: 80,
        left: 16,
        right: 16,
        zIndex: 10000,
        maxWidth: 400,
        margin: '0 auto',
        boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
      }}
    >
      {needRefresh ? (
        <Group mt="xs">
          <Button size="xs" onClick={updateServiceWorker}>
            Aggiorna
          </Button>
          <Button size="xs" variant="subtle" onClick={dismiss}>
            Dopo
          </Button>
        </Group>
      ) : (
        'Puoi usare l\'app anche senza connessione.'
      )}
    </Notification>
  )
}
