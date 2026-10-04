import DeleteOutline from '@mui/icons-material/DeleteOutline';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import type { AdminUser } from '../../api/types';

interface Props {
  user: AdminUser | null;
  onCancel: () => void;
  onConfirm: (user: AdminUser) => void;
}

export function DeleteUserDialog({ user, onCancel, onConfirm }: Props) {
  return (
    <Dialog
      open={user !== null}
      onClose={onCancel}
      aria-labelledby="delete-user-title"
      maxWidth="xs"
      fullWidth
    >
      <DialogTitle id="delete-user-title">Delete this user?</DialogTitle>
      <DialogContent>
        <DialogContentText>
          This permanently deletes {user?.email} and their data. This can’t be undone.
        </DialogContentText>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCancel}>Cancel</Button>
        <Button
          variant="contained"
          color="error"
          startIcon={<DeleteOutline />}
          onClick={() => {
            if (user) onConfirm(user);
          }}
        >
          Delete user
        </Button>
      </DialogActions>
    </Dialog>
  );
}
