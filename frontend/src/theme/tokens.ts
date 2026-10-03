export type ColorMode = 'light' | 'dark';

/** Design-system colour tokens. No other hues exist: `up` and `down` mean price direction, plus errors and
 * destructive actions (`down`), which are always paired with an icon and a word. */
export interface Tokens {
  bg: string;
  raised: string;
  line: string;
  ink: string;
  ink2: string;
  ink3: string;
  up: string;
  down: string;
}

export const tokens: Record<ColorMode, Tokens> = {
  light: {
    bg: '#FFFFFF',
    raised: '#F6F6F6',
    line: '#E3E3E3',
    ink: '#000000',
    ink2: '#3F3F3F',
    ink3: '#767676',
    up: '#12784A',
    down: '#C2342B',
  },
  dark: {
    bg: '#000000',
    raised: '#161616',
    line: '#2B2B2B',
    ink: '#FFFFFF',
    ink2: '#C4C4C4',
    ink3: '#8C8C8C',
    up: '#3DD68C',
    down: '#FF6B61',
  },
};

export const FONT_FAMILY = '"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif';

/** Layout constants shared by the shell and pages. */
export const layout = {
  topBarHeight: 56,
  contentMaxWidth: 1120,
  columnWidth: 1120 + 48, // content plus the 24px gutters
  sectionGap: 6, // spacing units: 6 * 8 = 48px
} as const;

/** Radii as strings: a bare number in MUI's `sx` is multiplied by the theme's 8px. */
export const radius = { sm: '8px', lg: '12px' } as const;

export const MOTION_MS = 150;
