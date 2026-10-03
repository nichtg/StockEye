import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import { focusSearch } from '../features/search/focusSearch';

/** Shown for /stock/:symbol when the server says it has never heard of the symbol. */
export function StockNotFound({ symbol }: { symbol: string }) {
  return (
    <Box sx={{ py: 6, maxWidth: 480 }}>
      <Typography variant="h1" gutterBottom>
        {symbol}
      </Typography>
      <Typography variant="h2" component="h2" gutterBottom>
        We couldn’t find that stock
      </Typography>
      <Typography sx={{ mb: 3 }}>
        Check the spelling, or search by company name. Singapore stocks end in .SI, for example
        D05.SI.
      </Typography>
      <Button variant="contained" onClick={focusSearch}>
        Search for a stock
      </Button>
    </Box>
  );
}
