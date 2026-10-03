import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import type { FindingOut, Reliability } from '../../api/types';
import { Term } from '../../components/Term';
import { RELIABILITY_LABEL, newsEventsPhrase, stripReliabilityLead } from './macroText';

const CHIP_STYLE = {
  likely_real: { bgcolor: 'ink', color: 'bg', borderColor: 'ink' },
  weak_evidence: { bgcolor: 'transparent', color: 'ink2', borderColor: 'ink3' },
  could_be_chance: { bgcolor: 'transparent', color: 'ink2', borderColor: 'ink3' },
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
        variant={value === 'likely_real' ? 'filled' : 'outlined'}
        sx={{ height: 22, ...CHIP_STYLE[value] }}
      />
      <Term id="statistical_reliability" />
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
            <>
              <Typography sx={{ color: 'ink' }}>{f.text}</Typography>
              {f.based_on_events > 0 && (
                <Typography variant="caption" sx={{ color: 'ink3' }}>
                  {newsEventsPhrase(f.based_on_events)}
                </Typography>
              )}
            </>
          )}
        </li>
      ))}
    </Box>
  );
}
