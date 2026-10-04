import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import Link from '@mui/material/Link';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useEffect, useRef, useState, type SyntheticEvent } from 'react';
import { Link as RouterLink, useLocation, useNavigate, useSearchParams } from 'react-router';
import { isApiError, userMessage } from '../../api/errors';
import { Wordmark } from '../../components/Wordmark';
import { useDocumentTitle } from '../../hooks';
import { useAuthMutation, type LoginNotice } from './useAuth';
import {
  MIN_PASSWORD_LENGTH,
  validateLogin,
  validateRegister,
  type FieldErrors,
} from './validation';

type Mode = 'login' | 'register';

const COPY = {
  login: {
    title: 'Log in',
    submit: 'Log in',
    switchPrompt: 'New to StockEye?',
    switchLink: 'Create an account',
    switchTo: '/register',
    passwordAutocomplete: 'current-password',
    emailAutocomplete: 'username',
  },
  register: {
    title: 'Create account',
    submit: 'Create account',
    switchPrompt: 'Already have an account?',
    switchLink: 'Log in',
    switchTo: '/login',
    passwordAutocomplete: 'new-password',
    emailAutocomplete: 'email',
  },
} as const;

function lengthHint(length: number): string {
  if (length === 0) return `At least ${MIN_PASSWORD_LENGTH} characters`;
  if (length >= MIN_PASSWORD_LENGTH)
    return `At least ${MIN_PASSWORD_LENGTH} characters: long enough`;
  return `At least ${MIN_PASSWORD_LENGTH} characters: ${MIN_PASSWORD_LENGTH - length} more to go`;
}

/** A one-line message the previous page left in router state, such as "Your account was deleted." */
function noticeFrom(state: unknown): string | undefined {
  const notice = (state as Partial<LoginNotice> | null)?.notice;
  return typeof notice === 'string' ? notice : undefined;
}

export function AuthForm({ mode }: { mode: Mode }) {
  const copy = COPY[mode];
  useDocumentTitle(copy.title);

  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  // Shown once: kept here, then dropped from the history entry so a reload doesn't repeat it.
  const [notice] = useState(() => noticeFrom(location.state));
  useEffect(() => {
    if (notice)
      void navigate(
        { pathname: location.pathname, search: location.search },
        { replace: true, state: null },
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, for the notice we arrived with
  }, []);
  const next = params.get('next');
  const switchTo = next ? `${copy.switchTo}?next=${encodeURIComponent(next)}` : copy.switchTo;

  const mutation = useAuthMutation(mode);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const focusFirstError = (found: FieldErrors) => {
    if (found.email) emailRef.current?.focus();
    else if (found.password) passwordRef.current?.focus();
  };

  const onSubmit = (event: SyntheticEvent) => {
    event.preventDefault();
    if (mutation.isPending) return;
    setFormError(null);

    const found =
      mode === 'login' ? validateLogin(email, password) : validateRegister(email, password);
    setErrors(found);
    if (found.email ?? found.password) {
      focusFirstError(found);
      return;
    }

    mutation.mutate(
      { email: email.trim(), password },
      {
        // On success the session query updates and the route guard redirects to `next` or home.
        onError: (error) => {
          if (!isApiError(error)) {
            setFormError(userMessage(error));
            return;
          }
          if (error.status === 401) {
            setFormError('Email or password is incorrect.');
            return;
          }
          const fromServer: FieldErrors = {};
          const emailMessage =
            error.fieldMessage('email') ?? (error.status === 409 ? error.message : undefined);
          const passwordMessage = error.fieldMessage('password');
          if (emailMessage) fromServer.email = emailMessage;
          if (passwordMessage) fromServer.password = passwordMessage;
          if (fromServer.email ?? fromServer.password) {
            setErrors(fromServer);
            focusFirstError(fromServer);
          } else {
            setFormError(userMessage(error));
          }
        },
      },
    );
  };

  const passwordHelper =
    errors.password ?? (mode === 'register' ? lengthHint(password.length) : undefined);

  return (
    <Box
      sx={{
        minHeight: '100dvh',
        display: 'flex',
        alignItems: { xs: 'flex-start', sm: 'center' },
        justifyContent: 'center',
        px: 2,
        py: 6,
      }}
    >
      <Box component="main" sx={{ width: '100%', maxWidth: 400 }}>
        <Box sx={{ mb: 4 }}>
          <Wordmark size="lg" />
        </Box>
        <Typography variant="h1" sx={{ mb: 3 }}>
          {copy.title}
        </Typography>

        {notice && (
          <Alert severity="info" icon={false} sx={{ mb: 3 }} role="status">
            {notice}
          </Alert>
        )}
        {formError && (
          <Alert severity="error" sx={{ mb: 3 }} role="alert">
            {formError}
          </Alert>
        )}

        <Box
          component="form"
          noValidate
          onSubmit={onSubmit}
          sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}
        >
          <TextField
            label="Email"
            name="email"
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setErrors((prev) => ({ ...prev, email: undefined }));
            }}
            error={Boolean(errors.email)}
            helperText={errors.email}
            fullWidth
            required
            inputRef={emailRef}
            slotProps={{
              htmlInput: {
                autoComplete: copy.emailAutocomplete,
                spellCheck: false,
                autoCapitalize: 'none',
              },
            }}
          />
          <TextField
            label="Password"
            name="password"
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setErrors((prev) => ({ ...prev, password: undefined }));
            }}
            error={Boolean(errors.password)}
            helperText={passwordHelper}
            fullWidth
            required
            inputRef={passwordRef}
            slotProps={{
              htmlInput: { autoComplete: copy.passwordAutocomplete, spellCheck: false },
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      edge="end"
                      size="small"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                      aria-pressed={showPassword}
                      onClick={() => {
                        setShowPassword((v) => !v);
                      }}
                    >
                      {showPassword ? (
                        <VisibilityOff fontSize="small" />
                      ) : (
                        <Visibility fontSize="small" />
                      )}
                    </IconButton>
                  </InputAdornment>
                ),
              },
            }}
          />
          <Button
            type="submit"
            variant="contained"
            size="large"
            loading={mutation.isPending}
            fullWidth
          >
            {copy.submit}
          </Button>
        </Box>

        <Typography variant="body2" sx={{ mt: 3 }}>
          {copy.switchPrompt}{' '}
          <Link component={RouterLink} to={switchTo}>
            {copy.switchLink}
          </Link>
        </Typography>
      </Box>
    </Box>
  );
}
