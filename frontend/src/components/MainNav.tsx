import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import { NavLink } from 'react-router';
import { NAV_ITEMS } from './navItems';

/**
 * Two quiet text links with a tab-style active indicator. They need about 140px, which does not fit beside the search, theme and
 * account buttons on a phone, so below `sm` the same links live in the account menu instead.
 * NavLink sets aria-current="page" on the active one.
 */
export function MainNav() {
  return (
    <Box
      component="nav"
      aria-label="Main"
      sx={{
        display: { xs: 'none', sm: 'flex' },
        // The bar's own gap is 12px (sm) / 24px (md); the extra margin makes it 32px after the wordmark.
        ml: { sm: 2.5, md: 1 },
        gap: 3,
        flexShrink: 0,
        alignSelf: 'stretch',
      }}
    >
      {NAV_ITEMS.map((item) => (
        <Link
          key={item.to}
          component={NavLink}
          to={item.to}
          end={item.to === '/'}
          underline="none"
          sx={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            color: 'ink2',
            fontSize: '0.875rem',
            // One weight in both states, so the active link never changes the row's width.
            fontWeight: 500,
            '&:hover': { color: 'ink' },
            // A 2px tab indicator on the bar's bottom edge; absolutely placed, so the text stays put.
            '&::after': {
              content: '""',
              position: 'absolute',
              left: 0,
              right: 0,
              bottom: 0,
              height: 2,
              bgcolor: 'ink',
              opacity: 0,
            },
            '&[aria-current="page"]': { color: 'ink' },
            '&[aria-current="page"]::after': { opacity: 1 },
          }}
        >
          {item.label}
        </Link>
      ))}
    </Box>
  );
}
