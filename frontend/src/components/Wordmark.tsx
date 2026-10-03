import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router';

/** The StockEye wordmark. Always links home. */
export function Wordmark({ size = 'md' }: { size?: 'md' | 'lg' }) {
  return (
    <Typography
      component={RouterLink}
      to="/"
      aria-label="StockEye home"
      sx={{
        color: 'ink',
        fontWeight: 600,
        fontSize: size === 'lg' ? '1.25rem' : '1.0625rem',
        letterSpacing: '-0.01em',
        textDecoration: 'none',
        borderRadius: 1,
      }}
    >
      StockEye
    </Typography>
  );
}
