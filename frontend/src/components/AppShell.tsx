import Box from '@mui/material/Box';
import { Suspense } from 'react';
import { Outlet } from 'react-router';
import { useMe } from '../features/auth/useAuth';
import { SearchBox } from '../features/search/SearchBox';
import { AccountMenu } from './AccountMenu';
import { MainNav } from './MainNav';
import { PageSkeleton } from './PageSkeleton';
import { SiteFrame } from './SiteFrame';
import { ThemeToggle } from './ThemeToggle';

export function AppShell() {
  const me = useMe();
  const user = me.data;

  return (
    <SiteFrame
      actions={
        <>
          <MainNav />
          <SearchBox />
          <Box sx={{ flex: 1, display: { xs: 'none', md: 'block' } }} />
          <ThemeToggle />
          {user && <AccountMenu user={user} />}
        </>
      }
    >
      <Suspense fallback={<PageSkeleton />}>
        <Outlet />
      </Suspense>
    </SiteFrame>
  );
}
