import Box from '@mui/material/Box';
import type { ReactNode } from 'react';
import { layout } from '../theme/tokens';
import { ThemeToggle } from './ThemeToggle';
import { Wordmark } from './Wordmark';

/** Minimal frame (wordmark, theme toggle) for states that appear before the real shell can. */
export function BareFrame({ children }: { children: ReactNode }) {
  return (
    <Box sx={{ maxWidth: layout.columnWidth, mx: 'auto', px: { xs: 2, md: 3 }, py: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Wordmark />
        <ThemeToggle />
      </Box>
      {children}
    </Box>
  );
}
