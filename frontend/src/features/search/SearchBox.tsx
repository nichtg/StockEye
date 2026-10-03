import Close from '@mui/icons-material/Close';
import ErrorOutline from '@mui/icons-material/ErrorOutline';
import SearchIcon from '@mui/icons-material/Search';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Dialog from '@mui/material/Dialog';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { useEffect, useRef, useState, type ReactNode, type Ref } from 'react';
import { useNavigate } from 'react-router';
import { userMessage } from '../../api/errors';
import type { SymbolMatch } from '../../api/types';
import { useDebouncedValue } from '../../hooks';
import { radius } from '../../theme/tokens';
import { useSymbolSearch } from '../stock/useStockData';
import { ExchangeTag } from './ExchangeTag';
import { FOCUS_SEARCH_EVENT, SEARCH_DEBOUNCE_MS } from './focusSearch';

const isMac = typeof navigator !== 'undefined' && /mac|iphone|ipad/i.test(navigator.userAgent);

function assignRef<T>(ref: Ref<T> | undefined, value: T | null): void {
  if (typeof ref === 'function') ref(value);
  else if (ref) (ref as { current: T | null }).current = value;
}

interface SearchFieldProps {
  onPick?: () => void;
  inputRef?: Ref<HTMLInputElement>;
  showShortcut?: boolean;
}

function SearchField({ onPick, inputRef, showShortcut }: SearchFieldProps) {
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const [open, setOpen] = useState(false);
  const trimmed = input.trim();
  const debounced = useDebouncedValue(trimmed, SEARCH_DEBOUNCE_MS);
  const search = useSymbolSearch(debounced);
  const waiting = trimmed !== debounced || search.isFetching;
  const options = trimmed && trimmed === debounced && search.data ? search.data : [];

  let emptyText: ReactNode = `No US or SGX stocks match “${trimmed}”.`;
  if (search.isError && !waiting) {
    emptyText = (
      <Typography
        component="span"
        variant="body2"
        role="alert"
        sx={{ color: 'ink2', display: 'flex', alignItems: 'flex-start', gap: 0.75 }}
      >
        <ErrorOutline sx={{ fontSize: 16, mt: '2px', flexShrink: 0 }} aria-hidden="true" />
        <span>{userMessage(search.error)} Keep typing to retry.</span>
      </Typography>
    );
  }

  return (
    <Autocomplete<SymbolMatch>
      fullWidth
      size="small"
      autoHighlight
      value={null}
      blurOnSelect
      open={open && trimmed.length > 0}
      onOpen={() => {
        setOpen(true);
      }}
      onClose={() => {
        setOpen(false);
      }}
      inputValue={input}
      onInputChange={(_e, value, reason) => {
        setInput(reason === 'reset' ? '' : value);
      }}
      onChange={(_e, match) => {
        if (!match) return;
        setInput('');
        onPick?.();
        void navigate(`/stock/${encodeURIComponent(match.symbol)}`);
      }}
      options={options}
      loading={waiting}
      loadingText="Searching…"
      noOptionsText={emptyText}
      filterOptions={(o) => o}
      getOptionLabel={(o) => o.symbol}
      isOptionEqualToValue={(a, b) => a.symbol === b.symbol}
      slotProps={{
        listbox: { sx: { py: 0.5 } },
        paper: { sx: { mt: 0.5, borderRadius: radius.sm } },
      }}
      renderOption={({ key, ...props }, option) => (
        <Box
          component="li"
          key={key}
          {...props}
          sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}
        >
          <Typography component="span" sx={{ fontWeight: 600, color: 'ink', flexShrink: 0 }}>
            {option.symbol}
          </Typography>
          <Typography
            component="span"
            noWrap
            variant="body2"
            sx={{ color: 'ink2', flex: 1, minWidth: 0 }}
          >
            {option.name}
          </Typography>
          <ExchangeTag exchange={option.exchange} />
        </Box>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          placeholder="Search for a stock…"
          slotProps={{
            htmlInput: {
              ...params.inputProps,
              'aria-label': 'Search for a stock',
              enterKeyHint: 'search',
              autoComplete: 'off',
              ref: (node: HTMLInputElement | null) => {
                assignRef(params.inputProps.ref, node);
                assignRef(inputRef, node);
              },
            },
            input: {
              ...params.InputProps,
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" sx={{ color: 'ink3' }} />
                </InputAdornment>
              ),
              endAdornment: showShortcut ? (
                <InputAdornment
                  position="end"
                  sx={{ display: input ? 'none' : 'flex', pointerEvents: 'none' }}
                >
                  <Typography
                    component="kbd"
                    variant="caption"
                    sx={{
                      color: 'ink3',
                      border: 1,
                      borderColor: 'line',
                      borderRadius: 1,
                      px: 0.75,
                      fontFamily: 'inherit',
                    }}
                  >
                    {isMac ? '⌘ K' : 'Ctrl K'}
                  </Typography>
                </InputAdornment>
              ) : undefined,
            },
          }}
        />
      )}
    />
  );
}

/** The top-bar stock search. Wide screens get the field; phones get an icon opening a sheet. */
export function SearchBox() {
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
  const [sheetOpen, setSheetOpen] = useState(false);
  const fieldRef = useRef<HTMLInputElement | null>(null);
  const sheetRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const focus = () => {
      if (compact) setSheetOpen(true);
      else fieldRef.current?.focus();
    };
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        focus();
      }
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener(FOCUS_SEARCH_EVENT, focus);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener(FOCUS_SEARCH_EVENT, focus);
    };
  }, [compact]);

  if (compact) {
    return (
      <Box sx={{ ml: 'auto' }}>
        <IconButton
          aria-label="Search for a stock"
          onClick={() => {
            setSheetOpen(true);
          }}
        >
          <SearchIcon />
        </IconButton>
        <Dialog
          fullScreen
          open={sheetOpen}
          onClose={() => {
            setSheetOpen(false);
          }}
          aria-label="Search for a stock"
          slotProps={{
            transition: {
              onEntered: () => {
                sheetRef.current?.focus();
              },
            },
            paper: { sx: { borderRadius: 0, border: 0 } },
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 2 }}>
            <SearchField
              inputRef={sheetRef}
              onPick={() => {
                setSheetOpen(false);
              }}
            />
            <IconButton
              aria-label="Close search"
              onClick={() => {
                setSheetOpen(false);
              }}
            >
              <Close />
            </IconButton>
          </Box>
        </Dialog>
      </Box>
    );
  }

  return (
    <Box sx={{ flex: 1, maxWidth: 480, minWidth: 0 }}>
      <SearchField inputRef={fieldRef} showShortcut />
    </Box>
  );
}
