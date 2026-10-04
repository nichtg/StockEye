import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { SignalOut } from '../../api/types';
import { Direction } from '../../components/Direction';
import { Term } from '../../components/Term';
import { signalTerm } from './technicalText';

function directionWord(direction: number): string {
  return direction > 0 ? 'Bullish' : direction < 0 ? 'Bearish' : 'Neutral';
}

/** One row per signal; a signal with zero weight is shown muted and marked as not counted. */
export function SignalList({ signals }: { signals: SignalOut[] }) {
  return (
    <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0 }}>
      {signals.map((s) => {
        const muted = s.weight === 0;
        return (
          <Box
            component="li"
            key={s.key}
            sx={{
              display: 'grid',
              gridTemplateColumns: '24px 1fr',
              columnGap: 1,
              py: 1.25,
              borderBottom: 1,
              borderColor: 'line',
              '&:first-of-type': { borderTop: 1, borderColor: 'line' },
            }}
          >
            <Box sx={{ textAlign: 'center', fontSize: '0.75rem', lineHeight: '1.7' }}>
              <Direction
                value={s.direction}
                digits={0}
                text={`${directionWord(s.direction)}:`}
                hideText
              />
            </Box>
            <Box>
              <Typography sx={{ color: muted ? 'ink3' : 'ink', fontWeight: 500 }}>
                <Term id={signalTerm(s.key)}>{s.label}</Term>
              </Typography>
              <Typography variant="body2" sx={{ color: muted ? 'ink3' : undefined }}>
                {s.detail}
              </Typography>
              {muted && (
                <Typography variant="caption" sx={{ color: 'ink3' }}>
                  Not counted in the outlook.
                </Typography>
              )}
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}
