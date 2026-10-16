import Skeleton from '@mui/material/Skeleton';

/** Stands in for the month control while the first page of "All" loads: chips (40px) or, on a phone, label plus select (64px). */
export function MonthChipsSkeleton() {
  return (
    <Skeleton
      variant="rounded"
      width={360}
      sx={{ maxWidth: '100%', mb: 2, height: { xs: 64, sm: 40 } }}
    />
  );
}
