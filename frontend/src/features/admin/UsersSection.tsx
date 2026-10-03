import SearchIcon from '@mui/icons-material/Search';
import Box from '@mui/material/Box';
import InputAdornment from '@mui/material/InputAdornment';
import Skeleton from '@mui/material/Skeleton';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { userMessage } from '../../api/errors';
import type { AdminUser, AdminUserPatch } from '../../api/types';
import { QueryRegion } from '../../components/QueryRegion';
import { SectionTitle } from '../../components/SectionTitle';
import { useNotice } from '../../components/useNotice';
import { useDebouncedValue } from '../../hooks';
import { useMe } from '../auth/useAuth';
import { DeleteUserDialog } from './DeleteUserDialog';
import { UserActionsMenu, type OpenMenu } from './UserActionsMenu';
import { UsersTable } from './UsersTable';
import { useAdminUsers, useDeleteUser, useUpdateUser } from './useAdmin';

export function UsersSection() {
  const me = useMe();
  // Search and page live in the URL (?q=&page=) so a filtered view can be shared or reloaded.
  const [params, setParams] = useSearchParams();
  const search = params.get('q') ?? '';
  const page = Math.max(1, Number(params.get('page')) || 1);
  const query = useDebouncedValue(search.trim(), 300);
  const users = useAdminUsers(query, page);
  const update = useUpdateUser();
  const remove = useDeleteUser();

  const [menu, setMenu] = useState<OpenMenu | null>(null);
  const [toDelete, setToDelete] = useState<AdminUser | null>(null);
  const notice = useNotice();

  const setView = (nextSearch: string, nextPage: number) => {
    const next = new URLSearchParams(params);
    if (nextSearch) next.set('q', nextSearch);
    else next.delete('q');
    if (nextPage > 1) next.set('page', String(nextPage));
    else next.delete('page');
    setParams(next, { replace: true });
  };

  const fail = (error: unknown) => {
    notice.show(userMessage(error));
  };

  const patch = (user: AdminUser, change: AdminUserPatch, success: string) => {
    setMenu(null);
    update.mutate(
      { id: user.id, patch: change },
      {
        onSuccess: () => {
          notice.show(success);
        },
        onError: fail,
      },
    );
  };

  const confirmDelete = (user: AdminUser) => {
    setToDelete(null);
    remove.mutate(user.id, {
      onSuccess: () => {
        notice.show(`Deleted ${user.email}`);
      },
      onError: fail,
    });
  };

  return (
    <Box component="section" aria-labelledby="users-heading">
      <SectionTitle id="users-heading">Users</SectionTitle>

      <TextField
        value={search}
        onChange={(e) => {
          setView(e.target.value, 1);
        }}
        placeholder="Search by email…"
        size="small"
        type="search"
        name="user-search"
        sx={{ width: { xs: '100%', sm: 320 }, mb: 2 }}
        slotProps={{
          htmlInput: {
            'aria-label': 'Search users by email',
            autoComplete: 'off',
            spellCheck: false,
          },
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          },
        }}
      />

      <QueryRegion
        query={users}
        skeleton={<Skeleton variant="rounded" height={260} />}
        errorTitle="Can’t load users"
      >
        {(data) =>
          data.items.length === 0 ? (
            <Typography sx={{ py: 3 }}>
              {query ? `No users match “${query}”.` : 'There are no users yet.'}
            </Typography>
          ) : (
            <UsersTable
              data={data}
              me={me.data?.id}
              page={page}
              onPage={(next) => {
                setView(search, next);
              }}
              onOpenMenu={setMenu}
            />
          )
        }
      </QueryRegion>

      <UserActionsMenu
        menu={menu}
        onClose={() => {
          setMenu(null);
        }}
        onPatch={patch}
        onDelete={(user) => {
          setMenu(null);
          setToDelete(user);
        }}
      />
      <DeleteUserDialog
        user={toDelete}
        onCancel={() => {
          setToDelete(null);
        }}
        onConfirm={confirmDelete}
      />

      {notice.element}
    </Box>
  );
}
