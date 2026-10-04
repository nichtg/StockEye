import Box from '@mui/material/Box';
import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Navigate, Outlet, useLocation } from 'react-router';
import { userMessage } from '../../api/errors';
import { signedOutOnPurposeKey } from '../../api/keys';
import { ErrorState } from '../../components/ErrorState';
import { PageSkeleton } from '../../components/PageSkeleton';
import { ThemeToggle } from '../../components/ThemeToggle';
import { Wordmark } from '../../components/Wordmark';
import { layout } from '../../theme/tokens';
import { useMe } from './useAuth';

/** Minimal frame (wordmark, theme toggle) for states that appear before the real shell can. */
function Bare({ children }: { children: ReactNode }) {
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

/** Gate for signed-in routes. Renders child routes only once the session is confirmed. */
export function RequireAuth() {
  const me = useMe();
  const location = useLocation();
  const client = useQueryClient();

  if (me.isPending)
    return (
      <Bare>
        <PageSkeleton />
      </Bare>
    );
  if (me.isError) {
    return (
      <Bare>
        <ErrorState
          title="Can’t load your account"
          message={userMessage(me.error)}
          onRetry={() => void me.refetch()}
        />
      </Bare>
    );
  }
  if (!me.data) {
    // Signed out on purpose (account deleted): there is nothing to come back to.
    if (client.getQueryData(signedOutOnPurposeKey)) return <Navigate to="/login" replace />;
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}
