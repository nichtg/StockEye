import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import Typography from '@mui/material/Typography';
import { layout } from '../theme/tokens';

/** Disclaimer and TradingView attribution, shown on every page. */
export function SiteFooter() {
  return (
    <Box component="footer" sx={{ borderTop: 1, borderColor: 'line', px: { xs: 2, md: 3 }, py: 3 }}>
      <Typography
        variant="body2"
        sx={{ color: 'ink3', maxWidth: layout.columnWidth - 48, mx: 'auto' }}
      >
        StockEye is an analysis tool, not investment advice. Data may be delayed.{' '}
        <Link
          href="https://www.tradingview.com/"
          target="_blank"
          rel="noopener noreferrer"
          sx={{ color: 'inherit', textDecorationColor: 'currentColor' }}
        >
          Charts by TradingView
        </Link>
      </Typography>
    </Box>
  );
}
