import DeleteOutline from '@mui/icons-material/DeleteOutline';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import TextField from '@mui/material/TextField';
import { useRef, useState, type SyntheticEvent } from 'react';
import { isApiError, userMessage } from '../../api/errors';
import { useDeleteAccount } from './useAuth';

interface Props {
  open: boolean;
  onClose: () => void;
}

/** Asks for the password again before the account and its watchlist are deleted for good. */
export function DeleteAccountDialog({ open, onClose }: Props) {
  const [password, setPassword] = useState('');
  const remove = useDeleteAccount();
  const passwordRef = useRef<HTMLInputElement>(null);

  // A wrong password belongs to the field; every other failure (last admin, rate limit) to the form.
  const error = remove.error;
  const fieldError =
    isApiError(error) && error.code === 'invalid_password' ? error.message : undefined;
  const formError = error && !fieldError ? userMessage(error) : undefined;

  const close = () => {
    if (!remove.isPending) onClose();
  };
  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    if (!password || remove.isPending) return;
    remove.mutate(password);
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      aria-labelledby="delete-account-title"
      aria-describedby="delete-account-description"
      maxWidth="xs"
      fullWidth
      slotProps={{
        transition: {
          onEntered: () => passwordRef.current?.focus(),
          onExited: () => {
            setPassword('');
            remove.reset();
          },
        },
      }}
    >
      <form noValidate onSubmit={submit}>
        <DialogTitle id="delete-account-title">Delete your account?</DialogTitle>
        <DialogContent>
          <DialogContentText id="delete-account-description" sx={{ mb: 2 }}>
            This permanently deletes your account and your watchlist. This can’t be undone.
          </DialogContentText>
          {formError && (
            <Alert severity="error" role="alert" sx={{ mb: 2 }}>
              {formError}
            </Alert>
          )}
          <TextField
            label="Password"
            name="password"
            type="password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              if (fieldError) remove.reset();
            }}
            error={Boolean(fieldError)}
            helperText={fieldError}
            fullWidth
            required
            inputRef={passwordRef}
            slotProps={{ htmlInput: { autoComplete: 'current-password', spellCheck: false } }}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={close} disabled={remove.isPending}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="contained"
            color="error"
            startIcon={<DeleteOutline />}
            loading={remove.isPending}
            disabled={!password}
          >
            Delete account
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
