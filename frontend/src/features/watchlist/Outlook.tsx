import Box from '@mui/material/Box';
import type { Lean } from '../../api/types';
import { leanLabel } from '../stock/technicalText';

const GLYPH: Record<Lean, string> = { bullish: '↗', neutral: '→', bearish: '↘' };

export function OutlookCell({ lean }: { lean: Lean | null }) {
  if (!lean)
    return (
      <Box component="span" sx={{ color: 'ink3' }}>
        –
      </Box>
    );
  return (
    <Box component="span" sx={{ whiteSpace: 'nowrap', color: 'ink' }}>
      <Box component="span" aria-hidden="true" sx={{ mr: 0.75, color: 'ink2' }}>
        {GLYPH[lean]}
      </Box>
      {leanLabel(lean)}
    </Box>
  );
}
