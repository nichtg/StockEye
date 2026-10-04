import Chip from '@mui/material/Chip';
import type { Exchange } from '../../lib/exchange';

/** Small outlined "US" / "SGX" tag. */
export function ExchangeTag({ exchange, label }: { exchange: Exchange; label?: string }) {
  return (
    <Chip
      size="small"
      variant="outlined"
      label={label ?? exchange}
      sx={{ height: 20, fontSize: '0.6875rem', '& .MuiChip-label': { px: 0.75 } }}
    />
  );
}
