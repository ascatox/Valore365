import { useSyncExternalStore } from 'react';
import type { MantineColorsTuple } from '@mantine/core';

/*
 * Colour theme of the app, chosen in Impostazioni > Generale and applied only
 * on phone-sized viewports: wider layouts always use the default (petrol).
 * The choice is stored on the device and is independent of light/dark.
 *
 * A theme swaps two Mantine tuples (see main.tsx): `teal`, the brand colour
 * used all over the app, and `dark`, the dark-mode neutrals. It also marks
 * <html> with data-v365-theme: index.html sets the same attribute before
 * first paint and has the rules that turn it into the light page background
 * (the dark one is dark[7]).
 */

export const COLOR_THEME_STORAGE_KEY = 'valore365.settings.colorTheme';
export const COLOR_THEME_ATTRIBUTE = 'data-v365-theme';
const MOBILE_QUERY = '(max-width: 48em)';

export type ColorThemeId = 'petrol' | 'ocean' | 'amethyst' | 'orchid' | 'bronze' | 'graphite';

export interface ColorTheme {
  id: ColorThemeId;
  label: string;
  /** Brand tuple: shade 6 is the light-mode fill/text, shade 4 the dark-mode text. */
  primary: MantineColorsTuple;
  /** Dark-mode neutrals: [7] page background, [6] cards and inputs, [4] borders. */
  dark: MantineColorsTuple;
  /** Light-mode page background; index.html repeats it (checked by a test). */
  lightPageBg: string;
  /** Main and second tone of the swatch in the picker. */
  swatch: [string, string];
}

export const DEFAULT_COLOR_THEME: ColorThemeId = 'petrol';

// Every tuple follows petrol's lightness steps: white on shade 6 and shade 4
// on dark[6]/dark[7] keep at least 4.5:1 contrast.
const THEME_COLORS: Record<ColorThemeId, Omit<ColorTheme, 'id' | 'swatch'>> = {
  petrol: {
    label: 'Petrolio',
    primary: [
      '#e7f4f2', '#cde8e4', '#9dd1c9', '#6bb8ad', '#3e9f93',
      '#1f877b', '#0f766e', '#0e6c65', '#0d625c', '#0b4a46',
    ],
    dark: [
      '#d3dcda', '#aab6b4', '#7c8987', '#55625f', '#2b3836',
      '#1b2726', '#151f1e', '#0e1514', '#0b1110', '#070c0b',
    ],
    lightPageBg: '#f5f7f7',
  },
  ocean: {
    label: 'Oceano',
    primary: [
      '#eaf1fe', '#d2e3ff', '#a5c6ff', '#75a8ff', '#4d8efe',
      '#266ee9', '#1d5fd0', '#1a57bf', '#184fae', '#123c84',
    ],
    dark: [
      '#d5dae3', '#adb3bf', '#7f8692', '#585f6b', '#2e3541',
      '#1e252f', '#181d26', '#10141a', '#0c1015', '#080b10',
    ],
    lightPageBg: '#f4f7fc',
  },
  amethyst: {
    label: 'Ametista',
    primary: [
      '#f0eeff', '#e1dcff', '#c5baff', '#af9cfe', '#9b7dfe',
      '#8050f0', '#6d3fd1', '#643ac0', '#5a34ae', '#442885',
    ],
    dark: [
      '#d9d8e2', '#b3b1be', '#868491', '#5f5d6a', '#353340',
      '#24232e', '#1d1b25', '#131219', '#100f15', '#0b0a0f',
    ],
    lightPageBg: '#f6f6fb',
  },
  // Magenta side of pink, so it doesn't read as the loss red.
  orchid: {
    label: 'Orchidea',
    primary: [
      '#feebf6', '#fed4ec', '#fba8da', '#f480c9', '#e45eb6',
      '#c13d96', '#ac3285', '#9e2e7a', '#8f2a6f', '#6d2054',
    ],
    dark: [
      '#e0d7dc', '#bbafb6', '#8e8289', '#675a62', '#3d3138',
      '#2b2127', '#231a1f', '#181115', '#130e11', '#0e090c',
    ],
    lightPageBg: '#faf5f8',
  },
  // Muted and on the yellow side, so it doesn't read as the attention orange.
  bronze: {
    label: 'Bronzo',
    primary: [
      '#f5f1e7', '#ebe3cd', '#d7c79f', '#c2ab71', '#ab904b',
      '#947a34', '#846c2b', '#796327', '#6e5a24', '#53441b',
    ],
    dark: [
      '#ddd9d1', '#b7b3a8', '#8a8579', '#635e52', '#393529',
      '#282419', '#201c13', '#16130d', '#120f0a', '#0d0b06',
    ],
    lightPageBg: '#f9f6f1',
  },
  graphite: {
    label: 'Grafite',
    primary: [
      '#eceff3', '#d8dee6', '#b7c1d0', '#99a7bc', '#8091a8',
      '#5d6d83', '#475569', '#414e60', '#3a4657', '#2b3441',
    ],
    dark: [
      '#d6dae1', '#aeb4bc', '#80868f', '#595f68', '#2f353e',
      '#1f252d', '#181d24', '#101418', '#0d1014', '#080b0f',
    ],
    lightPageBg: '#f5f7fa',
  },
};

export const COLOR_THEMES: ColorTheme[] = (Object.keys(THEME_COLORS) as ColorThemeId[]).map((id) => ({
  id,
  ...THEME_COLORS[id],
  swatch: [THEME_COLORS[id].primary[6], THEME_COLORS[id].primary[3]],
}));

const THEMES_BY_ID = Object.fromEntries(
  COLOR_THEMES.map((theme) => [theme.id, theme]),
) as Record<ColorThemeId, ColorTheme>;

export function getColorTheme(id: ColorThemeId): ColorTheme {
  return THEMES_BY_ID[id];
}

function isColorThemeId(value: unknown): value is ColorThemeId {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(THEMES_BY_ID, value);
}

// Fallback when localStorage is unavailable.
let sessionPreference: ColorThemeId | null = null;

export function getColorThemePreference(): ColorThemeId {
  try {
    const stored = window.localStorage.getItem(COLOR_THEME_STORAGE_KEY);
    return isColorThemeId(stored) ? stored : DEFAULT_COLOR_THEME;
  } catch {
    return sessionPreference ?? DEFAULT_COLOR_THEME;
  }
}

let currentPreference: ColorThemeId = DEFAULT_COLOR_THEME;
let currentActive: ColorThemeId = DEFAULT_COLOR_THEME;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Read the choice and the viewport again and apply them. Safe to call repeatedly. */
export function applyColorTheme() {
  if (typeof window === 'undefined') return;
  const preference = getColorThemePreference();
  const isPhone = window.matchMedia?.(MOBILE_QUERY).matches ?? false;
  const active = isPhone ? preference : DEFAULT_COLOR_THEME;
  document.documentElement.setAttribute(COLOR_THEME_ATTRIBUTE, active);
  if (preference !== currentPreference || active !== currentActive) {
    currentPreference = preference;
    currentActive = active;
    listeners.forEach((listener) => listener());
  }
}

/** Save the choice on this device and apply it right away. */
export function setColorThemePreference(preference: ColorThemeId) {
  const next = isColorThemeId(preference) ? preference : DEFAULT_COLOR_THEME;
  try {
    if (next === DEFAULT_COLOR_THEME) window.localStorage.removeItem(COLOR_THEME_STORAGE_KEY);
    else window.localStorage.setItem(COLOR_THEME_STORAGE_KEY, next);
    sessionPreference = null;
  } catch {
    // Storage blocked (private mode): the choice still applies for this visit.
    sessionPreference = next;
  }
  applyColorTheme();
}

/**
 * Apply now and again whenever the active theme may change: the viewport
 * crossing the phone breakpoint (rotation, resize) or another tab saving a
 * different choice.
 */
export function initColorTheme() {
  if (typeof window === 'undefined') return;
  applyColorTheme();
  window.matchMedia?.(MOBILE_QUERY).addEventListener?.('change', applyColorTheme);
  window.addEventListener('storage', (event) => {
    if (event.key === null || event.key === COLOR_THEME_STORAGE_KEY) applyColorTheme();
  });
}

/** The theme chosen on this device, even where it isn't applied (wide viewports). */
export function useColorThemePreference(): ColorThemeId {
  return useSyncExternalStore(subscribe, () => currentPreference, () => DEFAULT_COLOR_THEME);
}

/** The theme in use right now: the chosen one on phones, the default elsewhere. */
export function getActiveColorTheme(): ColorTheme {
  return THEMES_BY_ID[currentActive];
}

export function useActiveColorTheme(): ColorTheme {
  return useSyncExternalStore(subscribe, getActiveColorTheme, () => THEMES_BY_ID[DEFAULT_COLOR_THEME]);
}
