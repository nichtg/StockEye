import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Toolbar from '@mui/material/Toolbar';
import { Suspense, type ReactNode } from 'react';
import { Outlet } from 'react-router';
import { useMe } from '../features/auth/useAuth';
import { SearchBox } from '../features/search/SearchBox';
import { layout } from '../theme/tokens';
import { AccountMenu } from './AccountMenu';
import { PageSkeleton } from './PageSkeleton';
import { SiteFooter } from './SiteFooter';
import { ThemeToggle } from './ThemeToggle';
import { Wordmark } from './Wordmark';

export const MAIN_ID = 'main-content';
const gutter = { xs: 2, md: 3 };

/** Signed-in frame. Routes render through the outlet; a parent that is not a route passes children. */
export function AppShell({ children }: { children?: ReactNode }) {
  const me = useMe();
  const user = me.data;

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
          <SearchBox />
          <Box sx={{ flex: 1, display: { xs: 'none', md: 'block' } }} />
          <ThemeToggle />
          {user && <AccountMenu user={user} />}
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
          py: { xs: 3, md: 5 },
          outline: 'none',
        }}
      >
        <Suspense fallback={<PageSkeleton />}>{children ?? <Outlet />}</Suspense>
      </Box>

      <SiteFooter />
    </Box>
  );
}
