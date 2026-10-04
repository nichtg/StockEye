import { createContext, useContext } from 'react';

export interface NoticeAction {
  label: string;
  onClick: () => void;
}

export type Show = (message: string, action?: NoticeAction) => void;

export const NoticeContext = createContext<Show | null>(null);

/** A toast with an optional action (Undo), shown by the app's notice host. */
export function useNotice(): Show {
  const show = useContext(NoticeContext);
  if (!show) throw new Error('useNotice needs a NoticeProvider');
  return show;
}
