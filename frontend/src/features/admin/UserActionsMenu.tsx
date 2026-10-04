import DeleteOutline from '@mui/icons-material/DeleteOutline';
import ListItemIcon from '@mui/material/ListItemIcon';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Typography from '@mui/material/Typography';
import type { AdminUser, AdminUserPatch } from '../../api/types';

export interface OpenMenu {
  anchor: HTMLElement;
  user: AdminUser;
}

interface Props {
  menu: OpenMenu | null;
  onClose: () => void;
  onPatch: (user: AdminUser, change: AdminUserPatch, success: string) => void;
  onDelete: (user: AdminUser) => void;
}

/** Row actions for one user: toggle admin, toggle disabled, delete. */
export function UserActionsMenu({ menu, onClose, onPatch, onDelete }: Props) {
  return (
    <Menu anchorEl={menu?.anchor} open={menu !== null} onClose={onClose}>
      {menu && [
        <MenuItem
          key="role"
          disabled={menu.user.status === 'deleting'}
          onClick={() => {
            const isAdmin = menu.user.role === 'admin';
            onPatch(
              menu.user,
              { role: isAdmin ? 'user' : 'admin' },
              isAdmin
                ? `Removed admin from ${menu.user.email}`
                : `Made ${menu.user.email} an admin`,
            );
          }}
        >
          {menu.user.role === 'admin' ? 'Remove admin' : 'Make admin'}
        </MenuItem>,
        <MenuItem
          key="status"
          disabled={menu.user.status === 'deleting'}
          onClick={() => {
            const active = menu.user.status === 'active';
            onPatch(
              menu.user,
              { status: active ? 'disabled' : 'active' },
              active ? `Disabled ${menu.user.email}` : `Enabled ${menu.user.email}`,
            );
          }}
        >
          {menu.user.status === 'active' ? 'Disable' : 'Enable'}
        </MenuItem>,
        menu.user.status === 'deleting' && (
          <Typography
            key="why"
            variant="caption"
            component="li"
            role="none"
            sx={{ px: 2, py: 0.5, color: 'ink3' }}
          >
            This account is being deleted, so its role and status can’t change.
          </Typography>
        ),
        <MenuItem
          key="delete"
          onClick={() => {
            onDelete(menu.user);
          }}
          sx={{ color: 'down' }}
        >
          <ListItemIcon sx={{ color: 'inherit' }}>
            <DeleteOutline fontSize="small" />
          </ListItemIcon>
          Delete
        </MenuItem>,
      ]}
    </Menu>
  );
}
