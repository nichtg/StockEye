import { Navigate, Outlet, useSearchParams } from 'react-router';
import { safeNext } from './validation';
import { useMe } from './useAuth';

/**
 * Login and register routes. We do not wait for /me before showing the form, so the page works
 * even when the API is down; signing in updates /me, which triggers the redirect below.
 */
export function PublicOnly() {
  const me = useMe();
  const [params] = useSearchParams();
  if (me.data) return <Navigate to={safeNext(params.get('next'))} replace />;
  return <Outlet />;
}
