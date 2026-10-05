import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';
import { meKey } from '../../api/keys';
import { REFRESH_KEY, tokenStore } from '../../api/tokens';
import { stubFetch } from '../../test/mockApi';
import { useAuthMutation, useLogout } from './useAuth';

function setup() {
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

describe('session tokens', () => {
  it('login stores both tokens from the response body', async () => {
    stubFetch(() => ({
      body: {
        access_token: 'acc',
        access_expires_in: 900,
        refresh_token: 'ref',
        user: { id: '1', email: 'a@b.co', role: 'user', created_at: '2026-01-01T00:00:00Z' },
      },
    }));
    const { wrapper } = setup();
    const { result } = renderHook(() => useAuthMutation('login'), { wrapper });
    await act(() => result.current.mutateAsync({ email: 'a@b.co', password: 'x' }));
    expect(tokenStore.getAccess()).toBe('acc');
    expect(localStorage.getItem(REFRESH_KEY)).toBe('ref');
  });

  it('logout posts the refresh token, then clears storage and the cached user', async () => {
    tokenStore.set({ access: 'acc', refresh: 'ref' });
    const seen = stubFetch((req) => (req.path === '/auth/logout' ? { status: 204 } : undefined));
    const { client, wrapper } = setup();
    client.setQueryData(meKey, { id: '1' });
    const { result } = renderHook(() => useLogout(), { wrapper });
    await act(() => result.current.mutateAsync());
    await waitFor(() => {
      expect(seen).toHaveLength(1);
    });
    expect(seen[0]).toMatchObject({
      method: 'POST',
      path: '/auth/logout',
      body: { refresh_token: 'ref' },
    });
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
    expect(tokenStore.getAccess()).toBeNull();
    expect(client.getQueryData(meKey)).toBeNull();
  });
});
