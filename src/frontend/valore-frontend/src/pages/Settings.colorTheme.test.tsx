import { cleanup, fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { COLOR_THEMES, COLOR_THEME_STORAGE_KEY, applyColorTheme, setColorThemePreference } from '../colorTheme';
import { installFetchMock, renderWithApp, stubLayoutApis } from '../test/pageHarness';
import { SettingsPage } from './Settings.page';

const originalMatchMedia = window.matchMedia;

function setViewport(phone: boolean) {
  window.matchMedia = ((query: string) => ({
    ...originalMatchMedia(query),
    matches: phone && query === '(max-width: 48em)',
  })) as typeof window.matchMedia;
  applyColorTheme();
}

describe('Settings: colour theme picker', () => {
  beforeEach(() => {
    stubLayoutApis();
    installFetchMock([]);
  });

  afterEach(() => {
    cleanup();
    window.matchMedia = originalMatchMedia;
    setColorThemePreference('petrol');
    vi.unstubAllGlobals();
  });

  it('is shown on desktop viewports too, and picking applies the theme there', async () => {
    setViewport(false);
    renderWithApp(<SettingsPage />);
    const group = await screen.findByRole('radiogroup', { name: 'Tema colore' });
    expect(within(group).getAllByRole('radio')).toHaveLength(COLOR_THEMES.length);
    expect(screen.getByText('Vale per questo dispositivo.', { selector: '#color-theme-description' })).toBeInTheDocument();
    fireEvent.click(within(group).getByRole('radio', { name: 'Bronzo' }));
    expect(within(group).getByRole('radio', { name: 'Bronzo' })).toHaveAttribute('aria-checked', 'true');
    expect(document.documentElement.getAttribute('data-v365-theme')).toBe('bronze');
  });

  it('lists every theme on a phone, with the current one checked', async () => {
    setViewport(true);
    renderWithApp(<SettingsPage />);
    const group = await screen.findByRole('radiogroup', { name: 'Tema colore' });
    const options = within(group).getAllByRole('radio');
    expect(options.map((option) => option.textContent)).toEqual(COLOR_THEMES.map((theme) => theme.label));
    expect(within(group).getByRole('radio', { name: 'Petrolio' })).toHaveAttribute('aria-checked', 'true');
    expect(within(group).getByRole('radio', { name: 'Oceano' })).toHaveAttribute('aria-checked', 'false');
  });

  it('applies and stores a theme as soon as it is picked', async () => {
    setViewport(true);
    renderWithApp(<SettingsPage />);
    const group = await screen.findByRole('radiogroup', { name: 'Tema colore' });
    fireEvent.click(within(group).getByRole('radio', { name: 'Ametista' }));
    expect(within(group).getByRole('radio', { name: 'Ametista' })).toHaveAttribute('aria-checked', 'true');
    expect(within(group).getByRole('radio', { name: 'Petrolio' })).toHaveAttribute('aria-checked', 'false');
    expect(window.localStorage.getItem(COLOR_THEME_STORAGE_KEY)).toBe('amethyst');
    expect(document.documentElement.getAttribute('data-v365-theme')).toBe('amethyst');
  });

  it('offers the Christmas theme last, with a pine and red swatch', async () => {
    setViewport(false);
    renderWithApp(<SettingsPage />);
    const group = await screen.findByRole('radiogroup', { name: 'Tema colore' });
    const options = within(group).getAllByRole('radio');
    const natale = within(group).getByRole('radio', { name: 'Natale' });
    expect(options[options.length - 1]).toBe(natale);
    // Pine #2c7757 with a Christmas red #c3283a wedge (jsdom serialises them as rgb).
    const swatch = natale.querySelector<HTMLElement>('[aria-hidden]');
    expect(swatch?.getAttribute('style')).toContain('rgb(44, 119, 87) 0 76%, rgb(195, 40, 58) 76% 100%');
    fireEvent.click(natale);
    expect(natale).toHaveAttribute('aria-checked', 'true');
    expect(window.localStorage.getItem(COLOR_THEME_STORAGE_KEY)).toBe('christmas');
    expect(document.documentElement.getAttribute('data-v365-theme')).toBe('christmas');
  });

  it('moves the selection with the arrow keys', async () => {
    setViewport(true);
    renderWithApp(<SettingsPage />);
    const group = await screen.findByRole('radiogroup', { name: 'Tema colore' });
    const first = within(group).getByRole('radio', { name: 'Petrolio' });
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    const second = within(group).getByRole('radio', { name: 'Oceano' });
    expect(second).toHaveAttribute('aria-checked', 'true');
    expect(second).toHaveFocus();
    fireEvent.keyDown(second, { key: 'ArrowLeft' });
    fireEvent.keyDown(first, { key: 'ArrowLeft' });
    expect(within(group).getByRole('radio', { name: COLOR_THEMES[COLOR_THEMES.length - 1].label })).toHaveAttribute('aria-checked', 'true');
  });
});
