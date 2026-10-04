import { userMessage } from '../../api/errors';
import { useNotice } from '../../components/useNotice';
import { useWatchlistMutation } from './useWatchlist';

/**
 * Adds or removes a watchlist symbol and owns the feedback: a failure is explained, and every
 * removal offers its own Undo.
 */
export function useWatchlistToggle(): { toggle: (symbol: string, add: boolean) => void } {
  const mutation = useWatchlistMutation();
  const showNotice = useNotice();

  // mutateAsync rather than per-call callbacks: those are dropped if the caller unmounts first.
  const toggle = (symbol: string, add: boolean) => {
    mutation.mutateAsync({ symbol, add }).then(
      () => {
        if (!add) {
          showNotice(`Removed ${symbol}`, {
            label: 'Undo',
            onClick: () => {
              toggle(symbol, true);
            },
          });
        }
      },
      (error: unknown) => {
        showNotice(userMessage(error));
      },
    );
  };

  return { toggle };
}
