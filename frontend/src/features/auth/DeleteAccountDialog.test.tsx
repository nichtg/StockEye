import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router';
import { afterEach, describe, expect, it } from 'vitest';
import type { User } from '../../api/types';
import { AccountMenu } from '../../components/AccountMenu';
import { stubFetch, type MockHandler } from '../../test/mockApi';
import { renderApp } from '../../test/render';
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

  it('leaves for the login page with a notice once the account is gone', async () => {
    const { user } = await openDialog((req) =>
      req.method === 'DELETE' ? { status: 204 } : undefined,
    );
    await user.type(screen.getByLabelText(/Password/), 'a-password');
    await user.click(screen.getByRole('button', { name: 'Delete account' }));

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument();
    expect(screen.getByText('Your account was deleted.')).toBeInTheDocument();
  });
});
