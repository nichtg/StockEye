import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { discoverKey } from '../../api/keys';
import type { DiscoverOut } from '../../api/types';

/** The lists are rebuilt nightly, so a ten-minute cache loses nothing. */
const STALE_MS = 10 * 60 * 1000;

export function useDiscover() {
  return useQuery({
    queryKey: discoverKey,
    queryFn: ({ signal }) => api.get<DiscoverOut>('/discover', { signal }),
    staleTime: STALE_MS,
  });
}
