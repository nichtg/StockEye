import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import type { MacroReportOut } from '../../../api/types';

type Verdict = MacroReportOut['verdicts'][number];
type Kind = Verdict['answer_kind'];

// The word carries the meaning; strength shows as fill and weight, never as a good or bad colour.
const CHIP_STYLE: Record<Kind, object> = {
  clear: { bgcolor: 'ink', color: 'bg', borderColor: 'ink', fontWeight: 600 },
  possible: { bgcolor: 'transparent', color: 'ink', borderColor: 'ink', fontWeight: 500 },
  opposite: { bgcolor: 'transparent', color: 'ink', borderColor: 'ink', fontWeight: 600 },
  none: { bgcolor: 'transparent', color: 'ink2', borderColor: 'ink2', fontWeight: 400 },
  insufficient: { bgcolor: 'transparent', color: 'ink3', borderColor: 'ink3', fontWeight: 400 },
};

/** The section's answer first: one row per plain question, with a one-word chip and one line of support. */
export function VerdictList({ verdicts }: { verdicts: Verdict[] }) {
  return (
    <Box
      component="ul"
      aria-label="Answers"
      sx={{ listStyle: 'none', m: 0, p: 0, display: 'grid', gap: 2, maxWidth: 720 }}
    >
      {verdicts.map((v) => (
        <li key={v.id}>
          <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', columnGap: 1.5 }}>
            <Typography sx={{ color: 'ink' }}>{v.question}</Typography>
            <Chip
              size="small"
              label={v.answer}
              variant={v.answer_kind === 'clear' ? 'filled' : 'outlined'}
              data-kind={v.answer_kind}
              sx={{ height: 24, ...CHIP_STYLE[v.answer_kind] }}
            />
          </Box>
          <Typography variant="body2" sx={{ color: 'ink2', mt: 0.5 }}>
            {v.detail}
          </Typography>
        </li>
      ))}
    </Box>
  );
}
