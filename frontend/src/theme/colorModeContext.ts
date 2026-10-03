import { createContext, useContext } from 'react';
import type { ColorMode } from './tokens';

export interface ColorModeValue {
  /** The mode currently applied (explicit choice, otherwise the system preference). */
  mode: ColorMode;
  toggle: () => void;
}

export const ColorModeContext = createContext<ColorModeValue | null>(null);

export function useColorMode(): ColorModeValue {
  const value = useContext(ColorModeContext);
  if (!value) throw new Error('useColorMode must be used inside <ColorModeProvider>');
  return value;
}
