export const MIN_PASSWORD_LENGTH = 12;

export interface FieldErrors {
  email?: string;
  password?: string;
}

// Deliberately loose: the server is the authority, this only catches obvious typos.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateLogin(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {};
  if (!email.trim()) errors.email = 'Enter your email address.';
  else if (!EMAIL_PATTERN.test(email.trim()))
    errors.email = 'Enter a valid email address, like name@example.com.';
  if (!password) errors.password = 'Enter your password.';
  return errors;
}

export function validateRegister(email: string, password: string): FieldErrors {
  const errors = validateLogin(email, password);
  if (password && password.length < MIN_PASSWORD_LENGTH) {
    errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  } else if (!password) {
    errors.password = `Choose a password with at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  return errors;
}

/** Only same-site paths are allowed as a post-login destination (blocks open redirects). */
export function safeNext(next: string | null): string {
  if (next?.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\')) return next;
  return '/';
}
