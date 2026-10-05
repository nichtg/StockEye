import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { isApiError } from '../../api/errors';
import { meKey } from '../../api/keys';
import { tokenStore } from '../../api/tokens';
import type { Session, User } from '../../api/types';
import { useNotice } from '../../components/useNotice';
import { clearSession } from '../../queryClient';

export interface Credentials {
  email: string;
  password: string;
}

/** The signed-in user, or `null` when signed out. Network and server failures surface as errors. */
export function useMe() {
  return useQuery<User | null>({
    queryKey: meKey,
    queryFn: async ({ signal }) => {
      try {
        return await api.get<User>('/me', { signal });
      } catch (error) {
        if (isApiError(error) && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 5 * 60_000,
  });
}

/** Login and registration both start a session, so one mutation covers them. */
export function useAuthMutation(mode: 'login' | 'register') {
  const client = useQueryClient();
  return useMutation({
    // Tokens go straight to the token store and only the user is returned, so no token ever sits
    // in the query or mutation cache. gcTime 0 drops the mutation (and its password) on unmount.
    mutationFn: async (c: Credentials): Promise<User> => {
      const session = await api.post<Session>(`/auth/${mode}`, c);
      tokenStore.set({
        access: session.access_token,
        refresh: session.refresh_token,
        userId: session.user.id,
      });
      return session.user;
    },
    gcTime: 0,
    onSuccess: (user) => {
      client.setQueryData(meKey, user);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    // Fire and forget: the client signs this tab out at once and revokes server-side under the
    // refresh lock, so it sends the newest token. Storage is cleared there, not here.
    mutationFn: () => {
      void api.logout();
      return Promise.resolve();
    },
    onSettled: () => {
      clearSession(client, { localOnly: true });
    },
  });
}

const ACCOUNT_DELETED_NOTICE = 'Your account was deleted.';

/** Deletes the signed-in account after re-checking the password; the route guard then leaves for /login. */
export function useDeleteAccount() {
  const client = useQueryClient();
  const notice = useNotice();
  return useMutation({
    mutationFn: (password: string) => api.delete('/me', { body: { password } }),
    gcTime: 0,
    onSuccess: () => {
      // The toast lives above the routes, so it survives the redirect to the login page.
      notice(ACCOUNT_DELETED_NOTICE);
      clearSession(client, { onPurpose: true });
    },
  });
}
