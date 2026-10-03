import ErrorOutline from '@mui/icons-material/ErrorOutline';
import Box from '@mui/material/Box';
import LinearProgress from '@mui/material/LinearProgress';
import Skeleton from '@mui/material/Skeleton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { ProviderLevel, ProviderStatus } from '../../api/types';
import { QueryRegion } from '../../components/QueryRegion';
import { SectionTitle } from '../../components/SectionTitle';
import { Term } from '../../components/Term';
import { radius } from '../../theme/tokens';
import { formatAbsolute, formatReset } from './format';
import { LEVEL_LABEL, providerName } from './providerInfo';
import { useProviders } from './useAdmin';

/** Shape plus word carry the state; blocked adds an icon, and may use the error colour. */
function StatusDot({ level }: { level: ProviderLevel }) {
  if (level === 'blocked') {
    return <ErrorOutline aria-hidden="true" sx={{ fontSize: 14, color: 'down' }} />;
  }
  const base = {
    width: 10,
    height: 10,
    borderRadius: '50%',
    flexShrink: 0,
    boxSizing: 'border-box',
  } as const;
  const style = level === 'ok' ? { bgcolor: 'ink' } : { border: '2px solid', borderColor: 'ink' };
  return <Box component="span" aria-hidden="true" sx={{ ...base, ...style }} />;
}

function ProviderRow({ p }: { p: ProviderStatus }) {
  const name = providerName(p.provider);

  if (!p.configured) {
    return (
      <TableRow sx={{ '& td': { color: 'ink3' } }}>
        <TableCell component="th" scope="row" sx={{ color: 'ink3 !important', fontWeight: 500 }}>
          {name}
        </TableCell>
        <TableCell>Not configured</TableCell>
        <TableCell colSpan={3}>
          No API key is set on the server, so this source is skipped.
        </TableCell>
      </TableRow>
    );
  }

  const ratio = Math.min(Math.max(p.used_ratio, 0), 1);
  return (
    <TableRow>
      <TableCell component="th" scope="row" sx={{ color: 'ink !important', fontWeight: 500 }}>
        {name}
      </TableCell>
      <TableCell>
        <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1 }}>
          <StatusDot level={p.level} />
          {LEVEL_LABEL[p.level]}
        </Box>
      </TableCell>
      <TableCell sx={{ minWidth: 160 }}>
        <LinearProgress
          variant="determinate"
          value={ratio * 100}
          color={p.level === 'blocked' ? 'error' : 'primary'}
          aria-label={`${name} usage today`}
          sx={{ mb: 0.5 }}
        />
        {p.daily_limit === null ? `${p.used_today} used` : `${p.used_today} of ${p.daily_limit}`}
      </TableCell>
      <TableCell>{p.resets_at ? formatReset(p.resets_at) : 'Not set'}</TableCell>
      <TableCell sx={{ maxWidth: 320, minWidth: 200 }}>
        {p.last_error ? (
          <Tooltip
            title={
              p.last_error_at
                ? `${p.last_error} (${formatAbsolute(p.last_error_at)})`
                : p.last_error
            }
          >
            <Typography
              variant="body2"
              tabIndex={0}
              sx={{
                color: 'inherit',
                cursor: 'default',
                display: '-webkit-box',
                WebkitLineClamp: 3,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
                overflowWrap: 'anywhere',
              }}
            >
              {p.last_error}
            </Typography>
          </Tooltip>
        ) : (
          'None'
        )}
      </TableCell>
    </TableRow>
  );
}

export function ProvidersSection() {
  const providers = useProviders();

  return (
    <Box component="section" aria-labelledby="providers-heading">
      <SectionTitle id="providers-heading">Data providers</SectionTitle>
      <Typography variant="body2" sx={{ mb: 2, maxWidth: 640 }}>
        Each source has a daily <Term id="quota">quota</Term> of requests. If a source keeps
        failing, a <Term id="circuit_breaker">circuit breaker</Term> pauses requests to it for a
        while.
      </Typography>

      <QueryRegion
        query={providers}
        skeleton={<Skeleton variant="rounded" height={220} />}
        errorTitle="Can’t load data providers"
      >
        {(items) => (
          <TableContainer sx={{ border: 1, borderColor: 'line', borderRadius: radius.lg }}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Provider</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Usage today</TableCell>
                  <TableCell>Resets</TableCell>
                  <TableCell>Last error</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map((p) => (
                  <ProviderRow key={p.provider} p={p} />
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </QueryRegion>
    </Box>
  );
}
