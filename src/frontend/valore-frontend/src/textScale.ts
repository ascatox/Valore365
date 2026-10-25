import { useSyncExternalStore } from 'react';

/*
 * Root text size of the app, chosen in Impostazioni > Generale:
 * - "system" (default) follows the iOS text size on phones (see below) and
 *   stays at 16px elsewhere;
 * - the fixed sizes apply on every device.
 * The choice is stored on the device, like a browser zoom level.
 *
 * Following the iOS text size (Settings > Display & Brightness > Text Size,
 * and the larger accessibility sizes) on phones:
 *
 * Safari doesn't apply that setting to web pages, but it exposes it through
 * the system font keyword `-apple-system-body`: its size is 17px at the
 * default setting and grows or shrinks with the user's choice. We read it and
 * set the root font size from it. Mantine sizes text and spacing in rem, so
 * the whole interface follows. Other platforms and desktop keep 16px.
 */

const BASE_FONT_PX = 16;
// Size of -apple-system-body at the default iOS text size ("Large").
const IOS_DEFAULT_BODY_PX = 17;
// Beyond these the mobile layouts start to break; larger accessibility sizes
// are still honoured up to the cap.
export const MIN_TEXT_SCALE = 0.875;
export const MAX_TEXT_SCALE = 1.3;
// From this scale on, tight spots (e.g. bottom nav labels) switch layout.
export const LARGE_TEXT_SCALE = 1.15;

const MOBILE_QUERY = '(max-width: 48em)';
const STORAGE_KEY = 'valore365.settings.textSize';

export type TextSizePreference = 'system' | 'small' | 'normal' | 'large' | 'xlarge';

export const TEXT_SIZE_SCALES: Record<Exclude<TextSizePreference, 'system'>, number> = {
  small: 0.9,
  normal: 1,
  large: LARGE_TEXT_SCALE,
  xlarge: MAX_TEXT_SCALE,
};

function isTextSizePreference(value: unknown): value is TextSizePreference {
  return value === 'system' || (typeof value === 'string' && value in TEXT_SIZE_SCALES);
}

export function getTextSizePreference(): TextSizePreference {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isTextSizePreference(stored) ? stored : 'system';
  } catch {
    return 'system';
  }
}

// Fallback when localStorage is unavailable.
let sessionPreference: TextSizePreference | null = null;

/** Save the choice on this device and apply it right away. */
export function setTextSizePreference(preference: TextSizePreference) {
  try {
    if (preference === 'system') window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Storage blocked (private mode): the choice still applies for this visit.
  }
  sessionPreference = preference;
  applyTextScale();
}

/** Whether "system" can follow the OS text size here (iOS Safari / home-screen app). */
export function systemTextSizeSupported(): boolean {
  return typeof CSS !== 'undefined' && CSS.supports?.('font', '-apple-system-body') === true;
}

/** Root scale for a given -apple-system-body size, clamped to the supported range. */
export function textScaleFromIosBodySize(bodyPx: number): number {
  if (!Number.isFinite(bodyPx) || bodyPx <= 0) return 1;
  const scale = bodyPx / IOS_DEFAULT_BODY_PX;
  return Math.round(Math.min(MAX_TEXT_SCALE, Math.max(MIN_TEXT_SCALE, scale)) * 1000) / 1000;
}

function readIosBodySize(): number | null {
  if (typeof window === 'undefined' || !systemTextSizeSupported()) {
    return null;
  }
  const probe = document.createElement('span');
  probe.style.font = '-apple-system-body';
  probe.style.position = 'absolute';
  probe.style.visibility = 'hidden';
  probe.textContent = 'x';
  document.body.appendChild(probe);
  const size = parseFloat(window.getComputedStyle(probe).fontSize);
  probe.remove();
  return Number.isFinite(size) ? size : null;
}

let currentScale = 1;
const listeners = new Set<() => void>();

function setScale(scale: number) {
  const root = document.documentElement;
  if (scale === 1) {
    root.style.removeProperty('font-size');
  } else {
    root.style.fontSize = `${BASE_FONT_PX * scale}px`;
  }
  root.style.setProperty('--v365-text-scale', String(scale));
  root.classList.toggle('v365-large-text', scale >= LARGE_TEXT_SCALE);
  if (scale !== currentScale) {
    currentScale = scale;
    listeners.forEach((listener) => listener());
  }
}

/** Apply the chosen text size, or the iOS one for "system". Safe to call repeatedly. */
export function applyTextScale() {
  if (typeof window === 'undefined') return;
  const stored = getTextSizePreference();
  const preference = stored === 'system' && sessionPreference ? sessionPreference : stored;
  if (preference !== 'system') {
    setScale(TEXT_SIZE_SCALES[preference]);
    return;
  }
  const isPhone = window.matchMedia?.(MOBILE_QUERY).matches ?? false;
  const bodyPx = isPhone ? readIosBodySize() : null;
  setScale(bodyPx == null ? 1 : textScaleFromIosBodySize(bodyPx));
}

/**
 * Apply now and again whenever the user may have changed the setting: coming
 * back to the app (the setting is changed in iOS Settings) or switching
 * between phone and wider layouts.
 */
export function initTextScale() {
  if (typeof window === 'undefined') return;
  applyTextScale();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') applyTextScale();
  });
  window.matchMedia?.(MOBILE_QUERY).addEventListener?.('change', applyTextScale);
}

/** Current root text scale (1 = default), for sizes that can't be expressed in rem. */
export function useTextScale(): number {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => currentScale,
    () => 1,
  );
}
