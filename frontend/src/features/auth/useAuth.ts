import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { isApiError } from '../../api/errors';
import { meKey } from '../../api/keys';
import type { Session, User } from '../../api/types';
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
      client.setQueryData(meKey, session.user);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<undefined>('/auth/logout'),
    onSettled: () => {
      // Even if the call failed we drop local state; the cookies expire server-side regardless.
      clearSession(client);
    },
  });
}

export const ACCOUNT_DELETED_NOTICE = 'Your account was deleted.';

/** Deletes the signed-in account after re-checking the password; the route guard then leaves for /login. */
export function useDeleteAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (password: string) => api.delete('/me', { body: { password } }),
    onSuccess: () => {
      // Signing out sends RequireAuth to the login page, which shows the notice once.
      clearSession(client, ACCOUNT_DELETED_NOTICE);
    },
  });
}
