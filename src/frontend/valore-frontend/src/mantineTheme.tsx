import { Drawer, Modal, NumberInput, Tabs, createTheme, type MantineColorsTuple } from '@mantine/core';
import type { ColorTheme } from './colorTheme';

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
// `accent` colours the navigation chrome only (tabs, bottom nav): it is the
// brand tuple itself unless the theme has its own (Natale: Christmas red), so
// buttons, links, charts and values keep the brand and semantic colours.
export const buildTheme = (colorTheme: ColorTheme) => createTheme({
  primaryColor: 'teal',
  colors: {
    teal: colorTheme.primary,
    accent: colorTheme.accent,
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
    // Active tab indicator (default/outline border, pills fill) in the accent.
    // With an own accent the active label takes it too (see index.css), so the
    // tab reads in the accent and not only through its 2px underline.
    Tabs: Tabs.extend({
      defaultProps: { color: 'accent' },
      classNames: colorTheme.hasOwnAccent ? { tab: 'v365-accent-tab' } : undefined,
    }),
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
