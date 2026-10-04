import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AdminUser } from '../../api/types';
import { renderApp } from '../../test/render';
import { statusLabel } from './format';
import { UserActionsMenu } from './UserActionsMenu';

const user = (status: AdminUser['status']): AdminUser => ({
  id: 'u2',
  email: 'ann@example.com',
  role: 'user',
  status,
  created_at: '2026-02-01T00:00:00Z',
  last_login_at: null,
});

function open(status: AdminUser['status']) {
  renderApp(
    <UserActionsMenu
      menu={{ anchor: document.body, user: user(status) }}
      onClose={() => undefined}
      onPatch={() => undefined}
      onDelete={() => undefined}
    />,
  );
}

describe('user status', () => {
  it('words every status', () => {
    expect(statusLabel('active')).toBe('Active');
    expect(statusLabel('disabled')).toBe('Disabled');
    expect(statusLabel('deleting')).toBe('Being deleted');
  });

  it('offers no role or status change for an account being deleted', () => {
    open('deleting');
    expect(screen.getByRole('menuitem', { name: 'Make admin' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.getByRole('menuitem', { name: 'Enable' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.getByText(/being deleted, so its role and status/)).toBeInTheDocument();
  });

  it('keeps the actions on for an active account', () => {
    open('active');
    expect(screen.getByRole('menuitem', { name: 'Disable' })).not.toHaveAttribute('aria-disabled');
  });
});
