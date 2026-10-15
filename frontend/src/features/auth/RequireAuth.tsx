import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Navigate, Outlet, useLocation } from 'react-router';
import { userMessage } from '../../api/errors';
import { signedOutOnPurposeKey } from '../../api/keys';
import { tokenStore } from '../../api/tokens';
import { BareFrame } from '../../components/BareFrame';
import { ErrorState } from '../../components/ErrorState';
import { PageSkeleton } from '../../components/PageSkeleton';
import { useMe } from './useAuth';

/**
 * Gate for signed-in routes. Renders child routes only once the session is confirmed. A route
 * that is also meant for visitors passes `signedOut`, shown instead of the redirect to /login.
 */
export function RequireAuth({ signedOut }: { signedOut?: ReactNode }) {
  // No stored session means nobody is signed in here, so skip the /me round trip entirely.
  if (signedOut !== undefined && tokenStore.getRefresh() === null) return <>{signedOut}</>;
  return <Gate signedOut={signedOut} />;
}

function Gate({ signedOut }: { signedOut: ReactNode }) {
  const me = useMe();
  const location = useLocation();
  const client = useQueryClient();

  if (me.isPending)
    return (
      <BareFrame>
        <PageSkeleton />
      </BareFrame>
    );
  if (me.isError) {
    return (
      <BareFrame>
        <ErrorState
          title="Can’t load your account"
          message={userMessage(me.error)}
          onRetry={() => void me.refetch()}
        />
      </BareFrame>
    );
  }
  if (!me.data) {
    // Signed out on purpose (account deleted): there is nothing to come back to.
    if (client.getQueryData(signedOutOnPurposeKey)) return <Navigate to="/login" replace />;
    if (signedOut !== undefined) return <>{signedOut}</>;
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}
