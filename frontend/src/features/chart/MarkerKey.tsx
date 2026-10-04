import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import Tooltip from '@mui/material/Tooltip';
import { Term } from '../../components/Term';
import { MARKER_DEFS, emptyMarkerText, type MarkerKind } from './markers';

/**
 * Key to the chart's markers; each entry is also the switch that shows or hides that kind. It
 * counts what the chart's data holds, and a kind with nothing there is dimmed and says why. It
 * stays focusable (aria-disabled, not disabled) so keyboard users can reach the explanation.
 */
export function MarkerKey({
  shown,
  counts,
  onToggle,
}: {
  shown: MarkerKind[];
  /** Markers of each kind in the chart's current range; absent while the chart has no data. */
  counts: Record<MarkerKind, number> | undefined;
  onToggle: (kind: MarkerKind) => void;
}) {
  return (
    <Box
      component="ul"
      aria-label="Marker key"
      sx={{
        listStyle: 'none',
        display: 'flex',
        flexWrap: 'wrap',
        columnGap: 1,
        rowGap: 0.5,
        m: 0,
        mt: 1.5,
        p: 0,
      }}
    >
      {MARKER_DEFS.map((m) => {
        const count = counts?.[m.kind];
        const empty = count === 0;
        const on = shown.includes(m.kind) && !empty;
        return (
          <Box key={m.kind} component="li" sx={{ display: 'inline-flex', alignItems: 'center' }}>
            <Term id={m.term}>
              <Tooltip title={empty ? emptyMarkerText(m.kind) : ''} placement="top" describeChild>
                <ButtonBase
                  aria-pressed={on}
                  aria-disabled={empty}
                  aria-label={
                    count === undefined ? undefined : `${m.label}, ${String(count)} in this range`
                  }
                  onClick={() => {
                    if (!empty) onToggle(m.kind);
                  }}
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 0.75,
                    height: 28,
                    px: 1,
                    borderRadius: '999px',
                    border: 1,
                    borderColor: on ? 'line' : 'transparent',
                    bgcolor: on ? 'raised' : 'transparent',
                    color: on ? 'ink2' : 'ink3',
                    fontFamily: 'inherit',
                    fontSize: '0.8125rem',
                    transition: 'background-color 150ms ease',
                    '&:hover': { bgcolor: 'raised' },
                    ...(empty && { color: 'ink3', opacity: 0.6, cursor: 'default' }),
                  }}
                >
                  <Box
                    component="span"
                    aria-hidden="true"
                    sx={{
                      fontWeight: 600,
                      color: on ? 'ink' : 'ink3',
                      minWidth: 14,
                      textAlign: 'center',
                    }}
                  >
                    {m.glyph}
                  </Box>
                  {m.label}
                  {count !== undefined && (
                    <Box
                      component="span"
                      sx={{ color: 'ink3', fontVariantNumeric: 'tabular-nums' }}
                    >
                      {count}
                    </Box>
                  )}
                </ButtonBase>
              </Tooltip>
            </Term>
          </Box>
        );
      })}
    </Box>
  );
}
