import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import type { FindingOut, Reliability } from '../../api/types';
import { Term } from '../../components/Term';
import { RELIABILITY_LABEL, stripReliabilityLead } from './macroText';

const CHIP_STYLE = {
  // Strength shows as fill and weight on the monochrome scale, never as a good or bad colour.
  clear_effect: { bgcolor: 'ink', color: 'bg', borderColor: 'ink', fontWeight: 600 },
  possible_effect: { bgcolor: 'transparent', color: 'ink', borderColor: 'ink', fontWeight: 500 },
  no_clear_effect: { bgcolor: 'transparent', color: 'ink2', borderColor: 'ink3', fontWeight: 400 },
} as const;

function ReliabilityChip({ value }: { value: Reliability }) {
  return (
    <Box
      component="span"
      sx={{ display: 'inline-flex', alignItems: 'center', mr: 1, verticalAlign: 'middle' }}
    >
      <Chip
        size="small"
        label={RELIABILITY_LABEL[value]}
        variant={value === 'clear_effect' ? 'filled' : 'outlined'}
        sx={{ height: 22, ...CHIP_STYLE[value] }}
      />
      <Term id="news_effect" />
    </Box>
  );
}

/** Plain-sentence findings; a finding with a reliability verdict gets a chip, others a count. */
export function FindingList({ findings }: { findings: FindingOut[] }) {
  return (
    <Box
      component="ul"
      sx={{ listStyle: 'none', m: 0, p: 0, display: 'grid', gap: 1.25, maxWidth: 720 }}
    >
      {findings.map((f, i) => (
        <li key={`${String(i)}-${f.text}`}>
          {f.reliability ? (
            <Typography component="div">
              <ReliabilityChip value={f.reliability} />
              {stripReliabilityLead(f.text)}
            </Typography>
          ) : (
            <Typography sx={{ color: 'ink' }}>{f.text}</Typography>
          )}
        </li>
      ))}
    </Box>
  );
}
