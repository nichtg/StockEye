import type { CSSProperties } from 'react';

declare module '@mui/material/styles' {
  interface Palette {
    bg: string;
    raised: string;
    line: string;
    ink: string;
    ink2: string;
    ink3: string;
    up: string;
    down: string;
  }
  interface PaletteOptions {
    bg?: string;
    raised?: string;
    line?: string;
    ink?: string;
    ink2?: string;
    ink3?: string;
    up?: string;
    down?: string;
  }
  interface TypographyVariants {
    display: CSSProperties;
  }
  interface TypographyVariantsOptions {
    display?: CSSProperties;
  }
}

declare module '@mui/material/Typography' {
  interface TypographyPropsVariantOverrides {
    display: true;
  }
}
