import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { adminProvidersKey, adminUsersKey, adminUsersPageKey } from '../../api/keys';
import type { AdminUserPage, AdminUserPatch, ProviderStatus } from '../../api/types';

export const USERS_PAGE_SIZE = 20;
export const PROVIDERS_REFETCH_MS = 60_000;

export function useProviders() {
  return useQuery({
    queryKey: adminProvidersKey,
    queryFn: ({ signal }) => api.get<ProviderStatus[]>('/admin/providers', { signal }),
    refetchInterval: PROVIDERS_REFETCH_MS,
  });
}

/** `page` is 1-based, matching the API. */
export function useAdminUsers(query: string, page: number) {
  return useQuery({
    queryKey: adminUsersPageKey(query, page),
    queryFn: ({ signal }) =>
      api.get<AdminUserPage>('/admin/users', {
        signal,
        query: { query, page, page_size: USERS_PAGE_SIZE },
      }),
    placeholderData: keepPreviousData,
  });
}

export function useUpdateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: AdminUserPatch }) =>
      api.patch<unknown>(`/admin/users/${encodeURIComponent(id)}`, patch),
    onSettled: () => client.invalidateQueries({ queryKey: adminUsersKey }),
  });
}

export function useDeleteUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/admin/users/${encodeURIComponent(id)}`),
    onSettled: () => client.invalidateQueries({ queryKey: adminUsersKey }),
  });
}
