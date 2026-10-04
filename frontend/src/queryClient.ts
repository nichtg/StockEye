import { QueryClient } from '@tanstack/react-query';
import { api } from './api/client';
import { isApiError } from './api/errors';
import { meKey, signedOutOnPurposeKey } from './api/keys';

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
 * Forget everything cached for the signed-in user and mark them signed out. `onPurpose` (the user
 * deleted their account) is remembered so the route guard does not offer to come back to this page.
 * The signed-out mark goes last, so observers never see it without the flag.
 */
export function clearSession(client: QueryClient, { onPurpose = false } = {}): void {
  client.removeQueries({ predicate: (q) => q.queryKey[0] !== meKey[0] });
  if (onPurpose) client.setQueryData(signedOutOnPurposeKey, true);
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
