import { screen, waitFor } from '@testing-library/react';
import { useLocation } from 'react-router';
import { describe, expect, it } from 'vitest';
import { App } from '../../App';
import { signedOutOnPurposeKey } from '../../api/keys';
import { REFRESH_KEY } from '../../api/tokens';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';

const user = {
  id: 'u1',
  email: 'ann@example.com',
  role: 'user',
  created_at: '2026-01-01T00:00:00Z',
};

function Probe() {
  const { pathname, search } = useLocation();
  return <output data-testid="loc">{pathname + search}</output>;
}

function storeSession() {
  localStorage.setItem(REFRESH_KEY, JSON.stringify({ t: 'refresh', u: 'u1' }));
}

describe('RequireAuth on the home route', () => {
  it('shows the landing page at once, with no /me request, when no session is stored', () => {
    const seen = stubFetch(() => undefined);
    renderApp(<App />);

    expect(
      screen.getByRole('heading', { level: 1, name: 'See what moves your stocks' }),
    ).toBeInTheDocument();
    expect(seen).toEqual([]);
  });

  it('shows the watchlist when a stored session is confirmed', async () => {
    storeSession();
    stubFetch((req) => {
      if (req.path === '/me') return { body: user };
      if (req.path === '/watchlist/overview') return { body: [] };
      return undefined;
    });
    renderApp(<App />);

    expect(await screen.findByRole('heading', { level: 1, name: 'Watchlist' })).toBeInTheDocument();
  });

  it('shows the landing page when the stored session has expired', async () => {
    storeSession();
    stubFetch((req) =>
      req.path === '/me'
        ? { status: 401, body: { error: { code: 'unauthorized', message: 'no' } } }
        : undefined,
    );
    renderApp(<App />);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'See what moves your stocks' }),
    ).toBeInTheDocument();
  });

  it('shows the error state when /me fails', async () => {
    storeSession();
    stubFetch((req) =>
      req.path === '/me'
        ? { status: 500, body: { error: { code: 'server_error', message: 'boom' } } }
        : undefined,
    );
    renderApp(<App />);

    expect(await screen.findByText('Can’t load your account')).toBeInTheDocument();
  });

  it('sends a signed-out deep link to the login page with next', async () => {
    stubFetch((req) =>
      req.path === '/me'
        ? { status: 401, body: { error: { code: 'unauthorized', message: 'no' } } }
        : undefined,
    );
    renderApp(
      <>
        <App />
        <Probe />
      </>,
      { route: '/stock/AAPL' },
    );

    await waitFor(() => {
      expect(screen.getByTestId('loc')).toHaveTextContent('/login?next=%2Fstock%2FAAPL');
    });
  });

  it('goes to /login, not the landing page, after the account was deleted here', async () => {
    // Deletion clears the stored session, so this runs through the no-token short-circuit.
    const seen = stubFetch(() => undefined);
    renderApp(
      <>
        <App />
        <Probe />
      </>,
      { seed: (client) => client.setQueryData(signedOutOnPurposeKey, true) },
    );

    await waitFor(() => {
      expect(screen.getByTestId('loc').textContent).toBe('/login');
    });
    expect(seen.some((r) => r.path === '/me')).toBe(false);
  });
});
