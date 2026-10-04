import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { api } from '../../api/client';
import { ApiError } from '../../api/errors';
import { renderApp } from '../../test/render';
import { AuthForm } from './AuthForm';
import { safeNext, validateLogin, validateRegister } from './validation';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('validation', () => {
  it('flags empty and malformed emails and empty passwords on login', () => {
    expect(validateLogin('', '')).toEqual({
      email: 'Enter your email address.',
      password: 'Enter your password.',
    });
    expect(validateLogin('nope', 'x').email).toMatch(/valid email/);
    expect(validateLogin('a@b.co', 'x')).toEqual({});
  });

  it('requires 12 characters on register', () => {
    expect(validateRegister('a@b.co', 'x'.repeat(11)).password).toBe('Use at least 12 characters.');
    expect(validateRegister('a@b.co', 'x'.repeat(12))).toEqual({});
  });

  it('only accepts same-site next paths', () => {
    expect(safeNext('/stock/D05.SI')).toBe('/stock/D05.SI');
    expect(safeNext('//evil.example')).toBe('/');
    expect(safeNext('https://evil.example')).toBe('/');
    expect(safeNext(null)).toBe('/');
  });
});

describe('AuthForm', () => {
  it('shows inline errors and does not call the API when login is invalid', async () => {
    const post = vi.spyOn(api, 'post');
    const user = userEvent.setup();
    renderApp(<AuthForm mode="login" />);

    await user.click(screen.getByRole('button', { name: 'Log in' }));

    expect(screen.getByText('Enter your email address.')).toBeInTheDocument();
    expect(screen.getByText('Enter your password.')).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toHaveFocus();
    expect(post).not.toHaveBeenCalled();
  });

  it('uses the right autocomplete attributes and a toggle for the password', async () => {
    const user = userEvent.setup();
    renderApp(<AuthForm mode="register" />);

    expect(screen.getByLabelText(/email/i)).toHaveAttribute('autocomplete', 'email');
    const password = screen.getByLabelText(/^password/i);
    expect(password).toHaveAttribute('autocomplete', 'new-password');
    expect(password).toHaveAttribute('type', 'password');

    await user.click(screen.getByRole('button', { name: 'Show password' }));
    expect(password).toHaveAttribute('type', 'text');
  });

  it('shows the password rule up front and a live length hint on register', async () => {
    const user = userEvent.setup();
    renderApp(<AuthForm mode="register" />);
    expect(screen.getByText('At least 12 characters')).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^password/i), 'short');
    expect(screen.getByText('At least 12 characters: 7 more to go')).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^password/i), 'enough-now');
    expect(screen.getByText('At least 12 characters: long enough')).toBeInTheDocument();
  });

  it('shows a top alert for wrong credentials', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(
      new ApiError({ code: 'unauthenticated', message: 'nope', status: 401 }),
    );
    const user = userEvent.setup();
    renderApp(<AuthForm mode="login" />);

    await user.type(screen.getByLabelText(/email/i), 'a@b.co');
    await user.type(screen.getByLabelText(/^password/i), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Log in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect.');
  });

  it('maps server field details onto the matching field', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(
      new ApiError({
        code: 'validation_error',
        message: 'Password is too common.',
        status: 422,
        details: [{ field: 'password', message: 'Password is too common.' }],
      }),
    );
    const user = userEvent.setup();
    renderApp(<AuthForm mode="register" />);

    await user.type(screen.getByLabelText(/email/i), 'a@b.co');
    await user.type(screen.getByLabelText(/^password/i), 'password1234');
    await user.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => {
      expect(screen.getByText('Password is too common.')).toBeInTheDocument();
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
