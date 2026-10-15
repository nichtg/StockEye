import Skeleton from '@mui/material/Skeleton';

/** Stands in for the chip row while the first page of "All" (which carries the counts) loads. */
export function MonthChipsSkeleton() {
  return <Skeleton variant="rounded" width={360} height={40} sx={{ maxWidth: '100%', mb: 2 }} />;
}
