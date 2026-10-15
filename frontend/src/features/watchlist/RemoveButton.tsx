import Close from '@mui/icons-material/Close';
import IconButton from '@mui/material/IconButton';

export function RemoveButton({
  symbol,
  onRemove,
}: {
  symbol: string;
  onRemove: (symbol: string) => void;
}) {
  return (
    <IconButton
      size="small"
      aria-label={`Remove ${symbol} from watchlist`}
      onClick={(e) => {
        e.stopPropagation();
        onRemove(symbol);
      }}
      sx={{ color: 'ink3', '&:hover': { color: 'ink' } }}
    >
      <Close fontSize="small" />
    </IconButton>
  );
}
