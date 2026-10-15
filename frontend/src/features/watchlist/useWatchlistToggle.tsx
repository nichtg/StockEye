import { useState } from 'react';
import { userMessage } from '../../api/errors';
import { useNotice } from '../../components/useNotice';
import { useWatchlistMutation } from './useWatchlist';

interface Toggle {
  toggle: (symbol: string, add: boolean) => void;
  /** True while that symbol's add or remove request is in flight. */
  isPending: (symbol: string) => boolean;
}

/**
 * Adds or removes a watchlist symbol and owns the feedback: a failure is explained, and every
 * removal offers its own Undo.
 */
export function useWatchlistToggle(): Toggle {
  const mutation = useWatchlistMutation();
  const showNotice = useNotice();
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());

  const mark = (symbol: string, on: boolean) => {
    setPending((prev) => {
      const next = new Set(prev);
      if (on) next.add(symbol);
      else next.delete(symbol);
      return next;
    });
  };

  // mutateAsync rather than per-call callbacks: those are dropped if the caller unmounts first.
  const toggle = (symbol: string, add: boolean) => {
    mark(symbol, true);
    mutation.mutateAsync({ symbol, add }).then(
      () => {
        mark(symbol, false);
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
        mark(symbol, false);
        showNotice(userMessage(error));
      },
    );
  };

  return { toggle, isPending: (symbol) => pending.has(symbol) };
}
