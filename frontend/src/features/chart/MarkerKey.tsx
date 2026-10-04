import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import { Term } from '../../components/Term';
import { MARKER_DEFS, type MarkerKind } from './markers';

/** Key to the chart's markers; each entry is also the switch that shows or hides that kind. */
export function MarkerKey({
  shown,
  onToggle,
}: {
  shown: MarkerKind[];
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
        const on = shown.includes(m.kind);
        return (
          <Box key={m.kind} component="li" sx={{ display: 'inline-flex', alignItems: 'center' }}>
            <Term id={m.term}>
              <ButtonBase
                aria-pressed={on}
                onClick={() => {
                  onToggle(m.kind);
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
              </ButtonBase>
            </Term>
          </Box>
        );
      })}
    </Box>
  );
}
