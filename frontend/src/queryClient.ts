import { QueryClient } from '@tanstack/react-query';
import { api } from './api/client';
import { isApiError } from './api/errors';
import { meKey, signedOutNoticeKey } from './api/keys';

/**
 * Retrying a 4xx (including 429) never helps and a 429 would only make it worse; a dropped
 * connection or a 5xx is worth one more try.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (isApiError(error) && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: shouldRetry,
      },
    },
  });
}

/**
 * Forget everything cached for the signed-in user and mark them signed out. A `notice` is kept for
 * the login page to show once. The signed-out mark goes last, so observers never see it without
 * the notice.
 */
export function clearSession(client: QueryClient, notice?: string): void {
  client.removeQueries({ predicate: (q) => q.queryKey[0] !== meKey[0] });
  if (notice) client.setQueryData(signedOutNoticeKey, notice);
  client.setQueryData(meKey, null);
}

/**
 * When a refresh fails the session is gone: forget everything cached for that user and mark them
 * signed out. RequireAuth reacts to that by sending them to /login?next=<current path>.
 */
export function installSessionExpiry(client: QueryClient): void {
  api.setSessionExpiredHandler(() => {
    clearSession(client);
  });
}

export const queryClient = createQueryClient();
