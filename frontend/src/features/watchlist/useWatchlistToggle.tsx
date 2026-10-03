import type { ReactNode } from 'react';
import { userMessage } from '../../api/errors';
import { useNotice } from '../../components/useNotice';
import { useWatchlistMutation } from './useWatchlist';

/**
 * Adds or removes a watchlist symbol and owns the feedback: a failure is explained, and every
 * removal offers its own Undo. Render the returned `snackbar` once next to whatever calls `toggle`.
 */
export function useWatchlistToggle(): {
  toggle: (symbol: string, add: boolean) => void;
  snackbar: ReactNode;
} {
  const mutation = useWatchlistMutation();
  const notice = useNotice();

  // mutateAsync rather than per-call callbacks: those are dropped if the caller unmounts first.
  const toggle = (symbol: string, add: boolean) => {
    mutation.mutateAsync({ symbol, add }).then(
      () => {
        if (!add) {
          notice.show(`Removed ${symbol}`, {
            label: 'Undo',
            onClick: () => {
              toggle(symbol, true);
            },
          });
        }
      },
      (error: unknown) => {
        notice.show(userMessage(error));
      },
    );
  };

  return { toggle, snackbar: notice.element };
}
