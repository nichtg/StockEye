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
    mutationFn: (c: Credentials) => api.post<Session>(`/auth/${mode}`, c),
    onSuccess: (session) => {
      tokenStore.set({ access: session.access_token, refresh: session.refresh_token });
      client.setQueryData(meKey, session.user);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => {
      // Fire and forget: revoking server-side is best effort, signing out locally is not.
      const refreshToken = tokenStore.getRefresh();
      if (refreshToken) {
        api.post('/auth/logout', { refresh_token: refreshToken }).catch(() => undefined);
      }
      clearSession(client); // also clears the tokens
      return Promise.resolve();
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
    onSuccess: () => {
      // The toast lives above the routes, so it survives the redirect to the login page.
      notice(ACCOUNT_DELETED_NOTICE);
      clearSession(client, { onPurpose: true });
    },
  });
}
