import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { StockRow } from './sortFilter';

export function StaleNote({ row }: { row: StockRow }) {
  if (row.status === 'ok' || row.status === 'unavailable') return null;
  return (
    <Tooltip title={row.status_reason ?? 'This data may be out of date.'}>
      <Typography
        variant="caption"
        tabIndex={0}
        sx={{ display: 'block', color: 'ink3', cursor: 'help' }}
      >
        {row.status === 'stale' ? 'Delayed' : 'Partial data'}
      </Typography>
    </Tooltip>
  );
}
