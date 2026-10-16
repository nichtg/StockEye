import Box from '@mui/material/Box';
import type { ReactNode } from 'react';
import { CountBadge } from './CountBadge';

/** A name and its count badge on one shared baseline, 6px apart. */
export function LabelWithCount({
  children,
  count,
  inverted,
  hideBadgeFromSpeech = false,
}: {
  children: ReactNode;
  count: number;
  inverted?: boolean;
  /** For when the surrounding control already speaks the count. */
  hideBadgeFromSpeech?: boolean;
}) {
  return (
    <Box component="span" sx={{ display: 'inline-flex', alignItems: 'baseline', gap: '6px' }}>
      {children}
      <CountBadge count={count} inverted={inverted} silent={hideBadgeFromSpeech} />
    </Box>
  );
}
