import MoreVert from '@mui/icons-material/MoreVert';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { AdminUserPage } from '../../api/types';
import { visuallyHidden } from '../../lib/a11y';
import { radius } from '../../theme/tokens';
import { formatRelative } from '../../lib/format';
import { formatAbsolute, formatAdminDate, statusLabel } from './format';
import type { OpenMenu } from './UserActionsMenu';
import { USERS_PAGE_SIZE } from './useAdmin';

interface UsersTableProps {
  data: AdminUserPage;
  /** Id of the signed-in admin, marked "You" in the list. */
  me: string | undefined;
  /** 1-based, like the API. */
  page: number;
  onPage: (page: number) => void;
  onOpenMenu: (menu: OpenMenu) => void;
}

export function UsersTable({ data, me, page, onPage, onOpenMenu }: UsersTableProps) {
  return (
    <TableContainer sx={{ border: 1, borderColor: 'line', borderRadius: radius.lg }}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Email</TableCell>
            <TableCell>Role</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Created</TableCell>
            <TableCell>Last login</TableCell>
            <TableCell align="right">
              <Box component="span" sx={visuallyHidden}>
                Actions
              </Box>
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.items.map((u) => (
            <TableRow key={u.id}>
              <TableCell
                component="th"
                scope="row"
                sx={{ color: 'ink !important', fontWeight: 500 }}
              >
                {u.email}
                {u.id === me && (
                  <Typography component="span" variant="caption" sx={{ ml: 1, color: 'ink3' }}>
                    You
                  </Typography>
                )}
              </TableCell>
              <TableCell>{u.role === 'admin' ? 'Admin' : 'User'}</TableCell>
              <TableCell>{statusLabel(u.status)}</TableCell>
              <TableCell>{formatAdminDate(u.created_at)}</TableCell>
              <TableCell>
                {u.last_login_at ? (
                  <Tooltip title={formatAbsolute(u.last_login_at)}>
                    <Box component="time" dateTime={u.last_login_at} tabIndex={0}>
                      {formatRelative(u.last_login_at)}
                    </Box>
                  </Tooltip>
                ) : (
                  'Never'
                )}
              </TableCell>
              <TableCell align="right" sx={{ py: 0.5 }}>
                <IconButton
                  size="small"
                  aria-label={`Actions for ${u.email}`}
                  aria-haspopup="menu"
                  onClick={(e) => {
                    onOpenMenu({ anchor: e.currentTarget, user: u });
                  }}
                >
                  <MoreVert fontSize="small" />
                </IconButton>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <TablePagination
        component="div"
        count={data.total}
        page={page - 1}
        rowsPerPage={USERS_PAGE_SIZE}
        rowsPerPageOptions={[]}
        onPageChange={(_, zeroBased) => {
          onPage(zeroBased + 1);
        }}
        slotProps={{
          actions: {
            previousButton: { 'aria-label': 'Previous page' },
            nextButton: { 'aria-label': 'Next page' },
          },
        }}
      />
    </TableContainer>
  );
}
