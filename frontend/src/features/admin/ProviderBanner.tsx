import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import type { ProviderLevel } from '../../api/types';
import { useProviders } from './useAdmin';

const BANNERS: {
  level: ProviderLevel;
  severity: 'error' | 'warning';
  one: string;
  many: string;
}[] = [
  {
    level: 'blocked',
    severity: 'error',
    one: 'A data source is blocked',
    many: 'Data sources are blocked',
  },
  {
    level: 'warning',
    severity: 'warning',
    one: 'A data source is near its limit',
    many: 'Data sources are near their limit',
  },
];

/** Top-of-page alert, shown only when some data source is near its limit or blocked. */
export function ProviderBanner() {
  const { data } = useProviders();
  const shown = BANNERS.map((b) => ({
    ...b,
    messages: data?.filter((p) => p.level === b.level).map((p) => p.message) ?? [],
  })).filter((b) => b.messages.length > 0);
  if (shown.length === 0) return null;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mb: 4 }}>
      {shown.map((b) => (
        <Alert key={b.level} severity={b.severity}>
          <AlertTitle>{b.messages.length === 1 ? b.one : b.many}</AlertTitle>
          <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
            {b.messages.map((m) => (
              <Box component="li" key={m} sx={{ overflowWrap: 'anywhere' }}>
                {m}
              </Box>
            ))}
          </Box>
        </Alert>
      ))}
    </Box>
  );
}
