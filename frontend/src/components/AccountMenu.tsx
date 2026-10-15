import Avatar from '@mui/material/Avatar';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { useId, useState } from 'react';
import { Link as RouterLink, NavLink, useNavigate } from 'react-router';
import type { User } from '../api/types';
import { DeleteAccountDialog } from '../features/auth/DeleteAccountDialog';
import { useLogout } from '../features/auth/useAuth';
import { NAV_ITEMS } from './navItems';

export function AccountMenu({ user }: { user: User }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [deleting, setDeleting] = useState(false);
  const menuId = useId();
  const theme = useTheme();
  // Mounted only on phones: items hidden by CSS would still trap the arrow keys (see MainNav).
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
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
        {/* Phones only: the top bar has no room for these links there (see MainNav). */}
        {compact &&
          NAV_ITEMS.map((item) => (
            <MenuItem
              key={item.to}
              component={NavLink}
              to={item.to}
              end={item.to === '/'}
              onClick={close}
              sx={{ '&[aria-current="page"]': { fontWeight: 600 } }}
            >
              {item.label}
            </MenuItem>
          ))}
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
        <Divider />
        <MenuItem
          onClick={() => {
            close();
            setDeleting(true);
          }}
        >
          Delete account…
        </MenuItem>
      </Menu>
      <DeleteAccountDialog
        open={deleting}
        onClose={() => {
          setDeleting(false);
        }}
      />
    </>
  );
}
