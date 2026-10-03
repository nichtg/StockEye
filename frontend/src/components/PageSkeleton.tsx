import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import { radius } from '../theme/tokens';

/** Placeholder while a route's data loads. Shape mirrors a heading plus a block of content. */
export function PageSkeleton() {
  return (
    <Box aria-busy="true" aria-label="Loading…" role="status" sx={{ py: 4 }}>
      <Skeleton variant="text" width={180} sx={{ fontSize: '1.5rem' }} />
      <Skeleton variant="rounded" height={160} sx={{ mt: 2, borderRadius: radius.sm }} />
    </Box>
  );
}
