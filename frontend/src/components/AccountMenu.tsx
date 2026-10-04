import Avatar from '@mui/material/Avatar';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Typography from '@mui/material/Typography';
import { useId, useState } from 'react';
import { Link as RouterLink, useNavigate } from 'react-router';
import type { User } from '../api/types';
import { useLogout } from '../features/auth/useAuth';

export function AccountMenu({ user }: { user: User }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const menuId = useId();
  const navigate = useNavigate();
  const logout = useLogout();
  const close = () => {
    setAnchor(null);
  };

  return (
    <>
      <IconButton
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-controls={anchor ? menuId : undefined}
        aria-expanded={anchor ? 'true' : undefined}
        onClick={(e) => {
          setAnchor(e.currentTarget);
        }}
        sx={{ p: 0.5 }}
      >
        <Avatar sx={{ width: 32, height: 32 }}>{user.email.slice(0, 1).toUpperCase()}</Avatar>
      </IconButton>
      <Menu
        id={menuId}
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={close}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { minWidth: 220, mt: 0.5 } } }}
      >
        <Typography
          variant="body2"
          component="div"
          sx={{ px: 2, py: 1, color: 'ink3', maxWidth: 280, overflowWrap: 'anywhere' }}
        >
          Signed in as
          <Typography component="span" variant="subtitle2" sx={{ display: 'block', color: 'ink' }}>
            {user.email}
          </Typography>
        </Typography>
        <Divider />
        {user.role === 'admin' && (
          <MenuItem component={RouterLink} to="/admin" onClick={close}>
            Admin
          </MenuItem>
        )}
        <MenuItem
          onClick={() => {
            close();
            logout.mutate(undefined, {
              onSettled: () => void navigate('/login', { replace: true }),
            });
          }}
        >
          Log out
        </MenuItem>
      </Menu>
    </>
  );
}
