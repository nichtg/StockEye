import Box from '@mui/material/Box';
import { alpha, type Theme } from '@mui/material/styles';
import { visuallyHidden } from '../lib/a11y';
import { DIRECTION_GLYPH, directionOf, formatPct } from '../lib/format';
import { radius } from '../theme/tokens';

const COLOR = { up: 'up', down: 'down', flat: 'ink2' } as const;

/** Tint strength per mode. Light is 12% because red at 14% on white falls just under 4.5:1. */
const PILL_ALPHA = { light: 0.12, dark: 0.22 } as const;
const FLAT_ALPHA = 0.08;

type Dir = keyof typeof COLOR;

/** Pill background and text; contrast of each pairing is measured in the design-system spec. */
function pillSx(dir: Dir) {
  return (theme: Theme) => {
    const tint = dir === 'flat' ? theme.palette.ink : theme.palette[dir];
    return {
      bgcolor: alpha(tint, dir === 'flat' ? FLAT_ALPHA : PILL_ALPHA[theme.palette.mode]),
      color: dir === 'flat' ? theme.palette.ink2 : theme.palette[dir],
    };
  };
}

interface DirectionProps {
  /** Decides colour and glyph. Percent change by default, e.g. 0.86 for +0.86%. */
  value: number | null | undefined;
  /** Decimals that count when deciding direction (a rounded zero is flat). */
  digits?: number;
  /** Shown instead of the signed percent, e.g. "+0.36 (+0.86%)". */
  text?: string;
  /** Glyph only; the text stays available to screen readers. */
  hideText?: boolean;
  /** `pill` is a tinted box for tabular period-change cells; `text` (default) is plain coloured text. */
  variant?: 'text' | 'pill';
}

/** The one place direction is rendered: colour, glyph and sign together, never colour alone. */
export function Direction({ value, digits = 1, text, hideText, variant = 'text' }: DirectionProps) {
  if (value == null)
    return (
      <Box component="span" sx={{ color: 'ink3' }}>
        –
      </Box>
    );
  const dir = directionOf(value, digits);
  const glyph = DIRECTION_GLYPH[dir] || (hideText ? '–' : '');
  const label = text ?? formatPct(value, { signed: true, digits });
  const pill = variant === 'pill';
  return (
    <Box
      component="span"
      data-variant={variant}
      sx={[
        {
          color: COLOR[dir],
          whiteSpace: 'nowrap',
          fontVariantNumeric: 'tabular-nums',
          fontWeight: 500,
        },
        pill && {
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          minWidth: 72,
          px: '8px',
          py: '2px',
          borderRadius: radius.sm,
          fontWeight: 600,
        },
        pill && pillSx(dir),
      ]}
    >
      {glyph && (
        <Box
          component="span"
          aria-hidden="true"
          sx={{ fontSize: '0.75em', mr: hideText ? 0 : 0.5 }}
        >
          {glyph}
        </Box>
      )}
      <Box component="span" sx={hideText ? visuallyHidden : undefined}>
        {label}
      </Box>
    </Box>
  );
}
