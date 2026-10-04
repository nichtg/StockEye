import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

interface ErrorStateProps {
  title: string;
  message: string;
  onRetry?: () => void;
}

/** A failed data region: says what happened in plain words and offers the next step. */
export function ErrorState({ title, message, onRetry }: ErrorStateProps) {
  return (
    <Box role="alert" sx={{ py: 6, maxWidth: 480 }}>
      <Typography variant="h2" component="h2" gutterBottom>
        {title}
      </Typography>
      <Typography sx={{ mb: 2 }}>{message}</Typography>
      {onRetry && (
        <Button variant="outlined" onClick={onRetry}>
          Try again
        </Button>
      )}
    </Box>
  );
}
