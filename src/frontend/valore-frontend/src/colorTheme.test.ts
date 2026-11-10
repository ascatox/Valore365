import indexHtml from '../index.html?raw';
import {
  COLOR_THEMES,
  COLOR_THEME_ATTRIBUTE,
  COLOR_THEME_STORAGE_KEY,
  DEFAULT_COLOR_THEME,
  applyColorTheme,
  getActiveColorTheme,
  getColorTheme,
  getColorThemePreference,
  setColorThemePreference,
} from './colorTheme';

const MOBILE_QUERY = '(max-width: 48em)';
const originalMatchMedia = window.matchMedia;

function setViewport(phone: boolean) {
  window.matchMedia = ((query: string) => ({
    ...originalMatchMedia(query),
    matches: phone && query === MOBILE_QUERY,
  })) as typeof window.matchMedia;
}

const activeAttribute = () => document.documentElement.getAttribute(COLOR_THEME_ATTRIBUTE);

// WCAG 2 contrast ratio between two #rrggbb colours.
function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((start) => {
    const channel = parseInt(hex.slice(start, start + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

describe('colour themes', () => {
  it('offers the default and at least five more, each with a label', () => {
    expect(COLOR_THEMES.length).toBeGreaterThanOrEqual(6);
    expect(COLOR_THEMES[0].id).toBe(DEFAULT_COLOR_THEME);
    expect(new Set(COLOR_THEMES.map((theme) => theme.id)).size).toBe(COLOR_THEMES.length);
    COLOR_THEMES.forEach((theme) => expect(theme.label).not.toBe(''));
  });

  it.each(COLOR_THEMES)('$id has ten valid hex shades per tuple', (theme) => {
    [theme.primary, theme.dark].forEach((tuple) => {
      expect(tuple).toHaveLength(10);
      tuple.forEach((shade) => expect(shade).toMatch(/^#[0-9a-f]{6}$/));
    });
    [theme.lightPageBg, ...theme.swatch].forEach((color) => expect(color).toMatch(/^#[0-9a-f]{6}$/));
  });

  it.each(COLOR_THEMES)('$id keeps text readable in light and dark', (theme) => {
    expect(contrast('#ffffff', theme.primary[6])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(theme.primary[6], theme.lightPageBg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(theme.primary[4], theme.dark[6])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(theme.primary[4], theme.dark[7])).toBeGreaterThanOrEqual(4.5);
  });

  it('keeps the default theme on the petrol colours', () => {
    const petrol = getColorTheme('petrol');
    expect(petrol.primary[6]).toBe('#0f766e');
    expect(petrol.dark[7]).toBe('#0e1514');
    expect(petrol.lightPageBg).toBe('#f5f7f7');
  });
});

describe('colour theme preference', () => {
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    setColorThemePreference(DEFAULT_COLOR_THEME);
  });

  it('starts on the default theme', () => {
    setViewport(true);
    applyColorTheme();
    expect(getColorThemePreference()).toBe('petrol');
    expect(getActiveColorTheme().id).toBe('petrol');
    expect(activeAttribute()).toBe('petrol');
  });

  it('applies the chosen theme on a phone and remembers it', () => {
    setViewport(true);
    setColorThemePreference('ocean');
    expect(getColorThemePreference()).toBe('ocean');
    expect(window.localStorage.getItem(COLOR_THEME_STORAGE_KEY)).toBe('ocean');
    expect(getActiveColorTheme().id).toBe('ocean');
    expect(activeAttribute()).toBe('ocean');
  });

  it('goes back to the default without leaving a stored value', () => {
    setViewport(true);
    setColorThemePreference('bronze');
    setColorThemePreference('petrol');
    expect(window.localStorage.getItem(COLOR_THEME_STORAGE_KEY)).toBeNull();
    expect(activeAttribute()).toBe('petrol');
  });

  it('ignores an unknown stored value', () => {
    setViewport(true);
    window.localStorage.setItem(COLOR_THEME_STORAGE_KEY, 'fucsia');
    applyColorTheme();
    expect(getColorThemePreference()).toBe('petrol');
    expect(getActiveColorTheme().id).toBe('petrol');
    expect(activeAttribute()).toBe('petrol');
  });

  it('keeps the default theme on wider viewports, whatever the choice', () => {
    setViewport(false);
    setColorThemePreference('amethyst');
    expect(getColorThemePreference()).toBe('amethyst');
    expect(getActiveColorTheme().id).toBe('petrol');
    expect(activeAttribute()).toBe('petrol');
  });

  it('follows the viewport across the phone breakpoint', () => {
    setViewport(false);
    setColorThemePreference('graphite');
    setViewport(true);
    applyColorTheme();
    expect(getActiveColorTheme().id).toBe('graphite');
    setViewport(false);
    applyColorTheme();
    expect(getActiveColorTheme().id).toBe('petrol');
  });

  it('still applies the choice for the visit when storage is blocked', () => {
    setViewport(true);
    const blocked = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const unreadable = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    setColorThemePreference('orchid');
    expect(getActiveColorTheme().id).toBe('orchid');
    blocked.mockRestore();
    unreadable.mockRestore();
  });
});

// index.html sets the attribute before first paint and maps it to the light
// page background: it repeats values owned by colorTheme.ts.
describe('colour theme in index.html', () => {
  it('sets the attribute from the same key, on the same viewports', () => {
    expect(indexHtml).toContain(`localStorage.getItem('${COLOR_THEME_STORAGE_KEY}')`);
    expect(indexHtml).toContain(`matchMedia('${MOBILE_QUERY}')`);
    expect(indexHtml).toContain(`setAttribute('${COLOR_THEME_ATTRIBUTE}',t)`);
  });

  it('has the light page background of every theme but the default', () => {
    const rules = [...indexHtml.matchAll(
      /html\[data-v365-theme='(\w+)'\]:not\(\[data-mantine-color-scheme='dark'\]\) \{ --v365-page-bg: (#[0-9a-f]{6}); \}/g,
    )];
    const inHtml = Object.fromEntries(rules.map(([, id, color]) => [id, color]));
    const expected = Object.fromEntries(
      COLOR_THEMES.filter((theme) => theme.id !== DEFAULT_COLOR_THEME).map((theme) => [theme.id, theme.lightPageBg]),
    );
    expect(inHtml).toEqual(expected);
  });
});
