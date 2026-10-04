import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { Lean } from '../../api/types';
import { leanLabel } from './technicalText';

const TRACK = { position: 'absolute', left: 0, right: 0 } as const;

/** A -1..1 lean score as a dot on a neutral-centred track. */
export function ScoreBar({ score, lean }: { score: number; lean: Lean }) {
  const clamped = Math.max(-1, Math.min(1, score));
  const left = ((clamped + 1) / 2) * 100;
  const magnitude = Math.abs(clamped).toFixed(1);
  return (
    <Box sx={{ maxWidth: 360, mt: 1.5 }}>
      <Box
        role="meter"
        aria-label="Short-term lean"
        aria-valuemin={-1}
        aria-valuemax={1}
        aria-valuenow={Number(clamped.toFixed(2))}
        aria-valuetext={`${leanLabel(lean)}, score ${magnitude} of 1`}
        sx={{ position: 'relative', height: 16 }}
      >
        <Box sx={{ ...TRACK, top: 7, height: 2, bgcolor: 'line', borderRadius: 1 }} />
        <Box
          sx={{
            position: 'absolute',
            top: 3,
            left: '50%',
            width: '1px',
            height: 10,
            bgcolor: 'ink3',
          }}
        />
        <Box
          sx={{
            position: 'absolute',
            top: 2,
            left: `${String(left)}%`,
            width: 12,
            height: 12,
            ml: '-6px',
            borderRadius: '50%',
            bgcolor: 'ink',
            border: 2,
            borderColor: 'bg',
            boxSizing: 'content-box',
            transform: 'translate(-2px, -2px)',
          }}
        />
      </Box>
      <Box
        aria-hidden="true"
        sx={{
          position: 'relative',
          display: 'flex',
          justifyContent: 'space-between',
          mt: 0.5,
          color: 'ink3',
        }}
      >
        <Typography variant="caption">Bearish</Typography>
        <Typography
          variant="caption"
          sx={{ position: 'absolute', left: '50%', transform: 'translateX(-50%)' }}
        >
          Neutral
        </Typography>
        <Typography variant="caption">Bullish</Typography>
      </Box>
    </Box>
  );
}
