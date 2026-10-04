import Box from '@mui/material/Box';
import { visuallyHidden } from '../lib/a11y';
import { DIRECTION_GLYPH, directionOf, formatPct } from '../lib/format';

const COLOR = { up: 'up', down: 'down', flat: 'ink2' } as const;

interface DirectionProps {
  /** Decides colour and glyph. Percent change by default, e.g. 0.86 for +0.86%. */
  value: number | null | undefined;
  /** Decimals that count when deciding direction (a rounded zero is flat). */
  digits?: number;
  /** Shown instead of the signed percent, e.g. "+0.36 (+0.86%)". */
  text?: string;
  /** Glyph only; the text stays available to screen readers. */
  hideText?: boolean;
}

/** The one place direction is rendered: colour, glyph and sign together, never colour alone. */
export function Direction({ value, digits = 1, text, hideText }: DirectionProps) {
  if (value == null)
    return (
      <Box component="span" sx={{ color: 'ink3' }}>
        –
      </Box>
    );
  const dir = directionOf(value, digits);
  const glyph = DIRECTION_GLYPH[dir] || (hideText ? '–' : '');
  const label = text ?? formatPct(value, { signed: true, digits });
  return (
    <Box
      component="span"
      sx={{
        color: COLOR[dir],
        whiteSpace: 'nowrap',
        fontVariantNumeric: 'tabular-nums',
        fontWeight: 500,
      }}
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
