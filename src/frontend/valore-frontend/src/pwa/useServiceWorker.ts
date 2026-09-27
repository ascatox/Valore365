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
      if (!registration) return
      // Check for a new version whenever the app comes back to the foreground.
      // An installed iOS app is usually resumed rather than relaunched, so
      // neither a page load nor a background timer would trigger the check.
      const checkForUpdate = () => {
        if (document.visibilityState !== 'visible' || !navigator.onLine) return
        registration.update().catch(() => {})
      }
      // No periodic timer: with autoUpdate a new version reloads the page, which
      // is fine on resume but would discard in-progress input mid-session.
      document.addEventListener('visibilitychange', checkForUpdate)
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
