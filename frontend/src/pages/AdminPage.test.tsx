import { screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { App } from '../App';
import type { AdminUserPage, ProviderStatus, User } from '../api/types';
import { renderApp } from '../test/render';
import AdminPage from './AdminPage';

const admin: User = {
  id: 'u1',
  email: 'root@example.com',
  role: 'admin',
  created_at: '2026-01-01T00:00:00Z',
};

const providers: ProviderStatus[] = [
  {
    provider: 'yahoo',
    configured: true,
    used_today: 3,
    daily_limit: null,
    used_ratio: 0,
    resets_at: null,
    breaker_state: 'closed',
    last_error: null,
    last_error_at: null,
    level: 'ok',
    message: 'Working normally.',
  },
  {
    provider: 'finnhub',
    configured: true,
    used_today: 21,
    daily_limit: 25,
    used_ratio: 0.84,
    resets_at: '2026-10-04T00:00:00Z',
    breaker_state: 'closed',
    last_error: 'HTTP 429 from upstream while fetching company news for a symbol',
    last_error_at: '2026-10-03T08:00:00Z',
    level: 'warning',
    message: 'Finnhub has used 21 of its 25 daily requests.',
  },
  {
    provider: 'marketaux',
    configured: false,
    used_today: 0,
    daily_limit: 100,
    used_ratio: 0,
    resets_at: null,
    breaker_state: 'closed',
    last_error: null,
    last_error_at: null,
    level: 'ok',
    message: 'Not configured.',
  },
];

const users: AdminUserPage = {
  total: 1,
  items: [
    {
      id: 'u2',
      email: 'ann@example.com',
      role: 'user',
      status: 'active',
      created_at: '2026-02-01T00:00:00Z',
      last_login_at: null,
    },
  ],
};

function stubApi(me: User) {
  const requested: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string) => {
      const url = input;
      requested.push(url);
      const body = url.startsWith('/api/me')
        ? me
        : url.startsWith('/api/admin/providers')
          ? providers
          : url.startsWith('/api/admin/users')
            ? users
            : {};
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
  return requested;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AdminPage', () => {
  it('shows a warning banner that lists the affected provider message', async () => {
    stubApi(admin);
    renderApp(<AdminPage />);

    const banner = await screen.findByText('Finnhub has used 21 of its 25 daily requests.');
    const alert = banner.closest('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(
      within(alert as HTMLElement).getByText('A data source is near its limit'),
    ).toBeInTheDocument();
  });

  it('renders provider rows with human names, usage and a not-configured explanation', async () => {
    stubApi(admin);
    renderApp(<AdminPage />);

    expect(await screen.findByRole('rowheader', { name: 'Finnhub' })).toBeInTheDocument();
    expect(screen.getByText('21 of 25')).toBeInTheDocument();
    expect(screen.getByText('Near limit')).toBeInTheDocument();
    expect(screen.getByRole('rowheader', { name: 'Yahoo Finance' })).toBeInTheDocument();
    expect(screen.getByText(/No API key is set/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'What is quota?' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'What is circuit breaker?' })).toBeInTheDocument();
  });

  it('lists users and never requests a watchlist', async () => {
    const requested = stubApi(admin);
    renderApp(<AdminPage />);

    expect(await screen.findByText('ann@example.com')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Actions for ann@example.com' })).toBeInTheDocument();
    expect(requested.length).toBeGreaterThan(0);
    expect(requested.filter((u) => u.toLowerCase().includes('watchlist'))).toEqual([]);
  });
});

describe('admin route gating', () => {
  it('shows a plain not-found view to non-admins', async () => {
    const requested = stubApi({ ...admin, role: 'user' });
    renderApp(<App />, { route: '/admin' });

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
    expect(requested.some((u) => u.startsWith('/api/admin'))).toBe(false);
  });
});
