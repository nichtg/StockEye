import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useLocation } from 'react-router';
import { afterEach, describe, expect, it } from 'vitest';
import type { User } from '../../api/types';
import { AccountMenu } from '../../components/AccountMenu';
import { stubFetch, type MockHandler } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { App } from '../../App';
import { AuthForm } from './AuthForm';

const me: User = {
  id: 'u1',
  email: 'ann@example.com',
  role: 'user',
  created_at: '2026-01-01T00:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openDialog(handler: MockHandler) {
  const requests = stubFetch(handler);
  const user = userEvent.setup();
  renderApp(
    <Routes>
      <Route path="/" element={<AccountMenu user={me} />} />
      <Route path="/login" element={<AuthForm mode="login" />} />
    </Routes>,
  );
  await user.click(screen.getByRole('button', { name: 'Account menu' }));
  await user.click(screen.getByRole('menuitem', { name: /Delete account/ }));
  return { user, requests, dialog: await screen.findByRole('dialog') };
}

describe('delete account', () => {
  it('opens from the account menu and closes on Cancel', async () => {
    const { user, dialog } = await openDialog(() => undefined);
    expect(dialog).toHaveTextContent('Delete your account?');
    expect(dialog).toHaveTextContent(
      'This permanently deletes your account and your watchlist. This can’t be undone.',
    );
    expect(screen.getByLabelText(/Password/)).toHaveAttribute('autocomplete', 'current-password');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('shows a wrong password on the field', async () => {
    const { user, requests } = await openDialog((req) =>
      req.method === 'DELETE'
        ? {
            status: 403,
            body: { error: { code: 'invalid_password', message: 'That password is not correct.' } },
          }
        : undefined,
    );
    await user.type(screen.getByLabelText(/Password/), 'wrong-password');
    await user.click(screen.getByRole('button', { name: 'Delete account' }));

    expect(await screen.findByText('That password is not correct.')).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/)).toBeInvalid();
    expect(requests.find((r) => r.method === 'DELETE')).toMatchObject({
      path: '/me',
      body: { password: 'wrong-password' },
    });
  });

  it('sends any other 403, such as a CSRF failure, to the alert and not the field', async () => {
    const { user } = await openDialog((req) =>
      req.method === 'DELETE'
        ? {
            status: 403,
            body: { error: { code: 'csrf_failed', message: 'Security check failed.' } },
          }
        : undefined,
    );
    await user.type(screen.getByLabelText(/Password/), 'a-password');
    await user.click(screen.getByRole('button', { name: 'Delete account' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Security check failed.');
    expect(screen.getByLabelText(/Password/)).toBeValid();
  });

  it('focuses the password field when it opens and describes the dialog', async () => {
    const { dialog } = await openDialog(() => undefined);
    await waitFor(() => {
      expect(screen.getByLabelText(/Password/)).toHaveFocus();
    });
    expect(dialog).toHaveAccessibleDescription(/permanently deletes your account/);
  });

  it('shows the only-admin refusal as an alert', async () => {
    const message = 'You are the only admin. Make someone else an admin first.';
    const { user } = await openDialog((req) =>
      req.method === 'DELETE'
        ? { status: 409, body: { error: { code: 'last_admin', message } } }
        : undefined,
    );
    await user.type(screen.getByLabelText(/Password/), 'a-password');
    await user.click(screen.getByRole('button', { name: 'Delete account' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
  });
});

function LocationProbe() {
  const { pathname, search } = useLocation();
  return <p data-testid="location">{pathname + search}</p>;
}

describe('delete account through the real route guards', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('lands on /login with a toast that hides itself, and without a ?next= redirect', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let deleted = false;
    stubFetch((req) => {
      if (req.method === 'DELETE' && req.path === '/me') {
        deleted = true;
        return { status: 204 };
      }
      if (req.path === '/me') return deleted ? { status: 401 } : { body: me };
      if (req.path === '/watchlist') return { body: { items: [] } };
      return undefined;
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) });
    renderApp(
      <>
        <App />
        <LocationProbe />
      </>,
    );

    await user.click(await screen.findByRole('button', { name: 'Account menu' }));
    await user.click(await screen.findByRole('menuitem', { name: /Delete account/ }));
    await user.type(await screen.findByLabelText(/Password/), 'a-password');
    await user.click(screen.getByRole('button', { name: 'Delete account' }));

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument();
    expect(await screen.findByText('Your account was deleted.')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/login$/);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000);
    });
    await waitFor(() => {
      expect(screen.queryByText('Your account was deleted.')).not.toBeInTheDocument();
    });
  });
});
