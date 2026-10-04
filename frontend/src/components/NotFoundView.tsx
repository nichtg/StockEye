import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router';
import { useDocumentTitle } from '../hooks';

/** Also shown to non-admins on /admin, so the page's existence is not revealed. */
export function NotFoundView() {
  useDocumentTitle('Page not found');
  return (
    <Box sx={{ py: 6, maxWidth: 480 }}>
      <Typography variant="h1" gutterBottom>
        Page not found
      </Typography>
      <Typography sx={{ mb: 3 }}>
        The page you’re looking for doesn’t exist or has moved.
      </Typography>
      <Button component={RouterLink} to="/" variant="outlined">
        Go to watchlist
      </Button>
    </Box>
  );
}
