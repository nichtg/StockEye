import { QueryClient } from '@tanstack/react-query';
import { api } from './api/client';
import { isApiError } from './api/errors';
import { meKey, signedOutOnPurposeKey } from './api/keys';
import { tokenStore } from './api/tokens';

/**
 * Retrying a 4xx (including 429) never helps and a 429 would only make it worse; a dropped
 * connection or a 5xx is worth one more try.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (isApiError(error) && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}

/** The mark must outlive the moment nothing observes it, until the login page clears it. */
export function keepSignedOutMark(client: QueryClient): void {
  client.setQueryDefaults(signedOutOnPurposeKey, { gcTime: Infinity });
}

export function createQueryClient(): QueryClient {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: shouldRetry,
      },
    },
  });
  keepSignedOutMark(client);
  return client;
}

/**
 * Drop the tokens, forget everything cached for the signed-in user and mark them signed out. `onPurpose` (the user
 * deleted their account) is remembered so the route guard does not offer to come back to this page.
 * The signed-out mark goes last, so observers never see it without the flag.
 */
export function clearSession(client: QueryClient, { onPurpose = false } = {}): void {
  tokenStore.clear();
  client.removeQueries({ predicate: (q) => q.queryKey[0] !== meKey[0] });
  if (onPurpose) client.setQueryData(signedOutOnPurposeKey, true);
  client.setQueryData(meKey, null);
}

/**
 * When a refresh fails the session is gone: forget everything cached for that user and mark them
 * signed out. RequireAuth reacts to that by sending them to /login?next=<current path>.
 * A sign-out in another tab (the refresh token vanished from storage) does the same here.
 */
export function installSessionExpiry(client: QueryClient): void {
  api.setSessionExpiredHandler(() => {
    clearSession(client);
  });
  tokenStore.onSignedOutElsewhere(() => {
    clearSession(client);
  });
}

export const queryClient = createQueryClient();
