import { useRegisterSW } from 'virtual:pwa-register/react'

/**
 * Hook to manage PWA service worker registration and updates.
 *
 * Returns:
 * - needRefresh: true when a new version is available
 * - updateServiceWorker: call to apply the update
 * - offlineReady: true when app is cached and ready for offline use
 */
export function useServiceWorker() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    offlineReady: [offlineReady, setOfflineReady],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_swUrl, registration) {
      // Check for updates every 60 minutes
      if (registration) {
        setInterval(() => {
          registration.update()
        }, 60 * 60 * 1000)
      }
    },
    onRegisterError(error) {
      console.error('SW registration error:', error)
    },
  })

  function dismiss() {
    setNeedRefresh(false)
    setOfflineReady(false)
  }

  return {
    needRefresh,
    offlineReady,
    updateServiceWorker: () => updateServiceWorker(true),
    dismiss,
  }
}
