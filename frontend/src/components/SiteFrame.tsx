import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Toolbar from '@mui/material/Toolbar';
import type { ReactNode } from 'react';
import { layout } from '../theme/tokens';
import { SiteFooter } from './SiteFooter';
import { Wordmark } from './Wordmark';

export const MAIN_ID = 'main-content';
const gutter = { xs: 2, md: 3 };

/**
 * The page frame shared by the signed-in app and the landing page: skip link, sticky top bar with
 * the wordmark and a caller-supplied `actions` slot, the main landmark, and the footer.
 */
export function SiteFrame({
  actions,
  mainPaddingY = { xs: 3, md: 5 },
  children,
}: {
  actions: ReactNode;
  mainPaddingY?: { xs: number; md: number } | number;
  children: ReactNode;
}) {
  return (
    <Box sx={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column' }}>
      <Box
        component="a"
        href={`#${MAIN_ID}`}
        sx={{
          position: 'absolute',
          left: 16,
          top: -100,
          zIndex: (t) => t.zIndex.tooltip + 1,
          bgcolor: 'ink',
          color: 'bg',
          px: 2,
          py: 1,
          borderRadius: 1,
          '&:focus-visible': { top: 8, outlineColor: 'var(--mui-palette-bg)' },
        }}
      >
        Skip to content
      </Box>
      <AppBar
        position="sticky"
        color="inherit"
        elevation={0}
        sx={{ bgcolor: 'bg', borderBottom: 1, borderColor: 'line', backgroundImage: 'none' }}
      >
        <Toolbar
          disableGutters
          sx={{
            minHeight: layout.topBarHeight,
            px: gutter,
            gap: { xs: 1.5, md: 3 },
            maxWidth: layout.columnWidth,
            width: '100%',
            mx: 'auto',
          }}
        >
          <Wordmark />
          {actions}
        </Toolbar>
      </AppBar>

      <Box
        component="main"
        id={MAIN_ID}
        tabIndex={-1}
        sx={{
          flex: 1,
          width: '100%',
          maxWidth: layout.columnWidth,
          mx: 'auto',
          px: gutter,
          py: mainPaddingY,
          outline: 'none',
        }}
      >
        {children}
      </Box>

      <SiteFooter />
    </Box>
  );
}
