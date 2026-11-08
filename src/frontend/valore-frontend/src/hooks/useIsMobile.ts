import { useMediaQuery } from '@mantine/hooks';

export const MOBILE_MEDIA_QUERY = '(max-width: 48em)';

/**
 * True on phone-sized viewports.
 *
 * Mantine's useMediaQuery starts at `false` and reads the real value in an
 * effect, so every component that mounts (a page opened from the bottom nav)
 * paints one frame with its desktop layout before switching to mobile. The app
 * renders only in the browser, so read the media query during the first render.
 */
export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_MEDIA_QUERY, undefined, { getInitialValueInEffect: false });
}
