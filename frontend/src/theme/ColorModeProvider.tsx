import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { ColorModeContext } from './colorModeContext';
import { createAppTheme } from './createAppTheme';
import { tokens, type ColorMode } from './tokens';

export const COLOR_MODE_STORAGE_KEY = 'stockeye.color-mode';
const DARK_QUERY = '(prefers-color-scheme: dark)';

function readStoredMode(): ColorMode | null {
  try {
    const value = localStorage.getItem(COLOR_MODE_STORAGE_KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null; // storage can be blocked (private windows, strict settings)
  }
}

function writeStoredMode(mode: ColorMode): void {
  try {
    localStorage.setItem(COLOR_MODE_STORAGE_KEY, mode);
  } catch {
    // Not persisting is acceptable; the toggle still works for this session.
  }
}

function subscribeToSystem(onChange: () => void): () => void {
  if (typeof window.matchMedia !== 'function') return () => undefined;
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener('change', onChange);
  return () => {
    query.removeEventListener('change', onChange);
  };
}

function getSystemMode(): ColorMode {
  if (typeof window.matchMedia !== 'function') return 'light';
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
}

/** Defaults to the OS setting; once the user toggles, their choice wins and is remembered. */
export function ColorModeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoice] = useState<ColorMode | null>(readStoredMode);
  const system = useSyncExternalStore(subscribeToSystem, getSystemMode, (): ColorMode => 'light');
  const mode = choice ?? system;

  const toggle = useCallback(() => {
    const next: ColorMode = mode === 'dark' ? 'light' : 'dark';
    setChoice(next);
    writeStoredMode(next);
  }, [mode]);

  const theme = useMemo(() => createAppTheme(mode), [mode]);
  const value = useMemo(() => ({ mode, toggle }), [mode, toggle]);

  useEffect(() => {
    // Keep the browser chrome (mobile address bar) in step with an explicit choice.
    const metas = document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]');
    metas.forEach((meta) => {
      meta.content = tokens[mode].bg;
      meta.removeAttribute('media');
    });
  }, [mode]);

  return (
    <ColorModeContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        <CssBaseline enableColorScheme />
        {children}
      </ThemeProvider>
    </ColorModeContext.Provider>
  );
}
