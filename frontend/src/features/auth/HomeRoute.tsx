import { useQueryClient } from '@tanstack/react-query';
import { Navigate } from 'react-router';
import { userMessage } from '../../api/errors';
import { signedOutOnPurposeKey } from '../../api/keys';
import { tokenStore } from '../../api/tokens';
import { AppShell } from '../../components/AppShell';
import { BareFrame } from '../../components/BareFrame';
import { ErrorState } from '../../components/ErrorState';
import { PageSkeleton } from '../../components/PageSkeleton';
import HomePage from '../../pages/HomePage';
import LandingPage from '../../pages/LandingPage';
import { useMe } from './useAuth';

function SessionHome() {
  const me = useMe();
  const client = useQueryClient();

  if (me.isPending)
    return (
      <BareFrame>
        <PageSkeleton />
      </BareFrame>
    );
  if (me.isError)
    return (
      <BareFrame>
        <ErrorState
          title="Can’t load your account"
          message={userMessage(me.error)}
          onRetry={() => void me.refetch()}
        />
      </BareFrame>
    );
  if (!me.data) {
    // Account deleted from this tab: keep the existing behaviour of leaving for the login page.
    if (client.getQueryData(signedOutOnPurposeKey)) return <Navigate to="/login" replace />;
    return <LandingPage />;
  }
  return (
    <AppShell>
      <HomePage />
    </AppShell>
  );
}

/**
 * The `/` route. Visitors with no stored session see the landing page at once, without asking the
 * API who they are; a stored session is confirmed through /me first.
 */
export function HomeRoute() {
  if (tokenStore.getRefresh() === null) return <LandingPage />;
  return <SessionHome />;
}
