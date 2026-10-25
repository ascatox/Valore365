import {
  MAX_TEXT_SCALE,
  MIN_TEXT_SCALE,
  getTextSizePreference,
  setTextSizePreference,
  textScaleFromIosBodySize,
} from './textScale';

describe('textScaleFromIosBodySize', () => {
  it('keeps the default iOS text size at scale 1', () => {
    expect(textScaleFromIosBodySize(17)).toBe(1);
  });

  it('follows larger and smaller iOS text sizes', () => {
    expect(textScaleFromIosBodySize(19)).toBeCloseTo(19 / 17, 3);
    expect(textScaleFromIosBodySize(15)).toBeCloseTo(15 / 17, 3);
  });

  it('caps the accessibility sizes so the mobile layout holds', () => {
    expect(textScaleFromIosBodySize(53)).toBe(MAX_TEXT_SCALE);
    expect(textScaleFromIosBodySize(12)).toBe(MIN_TEXT_SCALE);
  });

  it('falls back to 1 for unreadable sizes', () => {
    expect(textScaleFromIosBodySize(Number.NaN)).toBe(1);
    expect(textScaleFromIosBodySize(0)).toBe(1);
  });
});

describe('text size preference', () => {
  afterEach(() => {
    setTextSizePreference('system');
  });

  it('applies a fixed size on any device and remembers it', () => {
    setTextSizePreference('large');
    expect(document.documentElement.style.fontSize).toBe('18.4px');
    expect(document.documentElement.classList.contains('v365-large-text')).toBe(true);
    expect(getTextSizePreference()).toBe('large');
  });

  it('goes back to the standard size with "system" where iOS text size is not available', () => {
    setTextSizePreference('xlarge');
    setTextSizePreference('system');
    expect(document.documentElement.style.fontSize).toBe('');
    expect(document.documentElement.classList.contains('v365-large-text')).toBe(false);
    expect(window.localStorage.getItem('valore365.settings.textSize')).toBeNull();
  });

  it('ignores an unknown stored value', () => {
    window.localStorage.setItem('valore365.settings.textSize', 'enorme');
    expect(getTextSizePreference()).toBe('system');
  });
});
