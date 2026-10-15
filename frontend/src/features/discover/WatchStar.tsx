import Star from '@mui/icons-material/Star';
import StarBorder from '@mui/icons-material/StarBorder';
import IconButton from '@mui/material/IconButton';

interface Props {
  symbol: string;
  inList: boolean;
  /** True until the watchlist is known, so a click cannot add something already saved. */
  disabled: boolean;
  onToggle: (symbol: string, add: boolean) => void;
}

/** A watchlist star for one Discover row. The caller owns the single add/remove mutation. */
export function WatchStar({ symbol, inList, disabled, onToggle }: Props) {
  return (
    <IconButton
      size="small"
      disabled={disabled}
      aria-label={inList ? `Remove ${symbol} from watchlist` : `Add ${symbol} to watchlist`}
      onClick={(e) => {
        e.stopPropagation();
        onToggle(symbol, !inList);
      }}
      sx={{ color: inList ? 'ink' : 'ink3', '&:hover': { color: 'ink' } }}
    >
      {inList ? <Star fontSize="small" /> : <StarBorder fontSize="small" />}
    </IconButton>
  );
}
