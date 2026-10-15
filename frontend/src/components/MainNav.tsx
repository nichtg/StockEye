import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import { NavLink } from 'react-router';
import { NAV_ITEMS } from './navItems';

/**
 * Two quiet text links. They need about 140px, which does not fit beside the search, theme and
 * account buttons on a phone, so below `sm` the same links live in the account menu instead.
 * NavLink sets aria-current="page" on the active one.
 */
export function MainNav() {
  return (
    <Box
      component="nav"
      aria-label="Main"
      sx={{ display: { xs: 'none', sm: 'flex' }, gap: 2, flexShrink: 0 }}
    >
      {NAV_ITEMS.map((item) => (
        <Link
          key={item.to}
          component={NavLink}
          to={item.to}
          end={item.to === '/'}
          underline="none"
          sx={{
            color: 'ink3',
            fontSize: '0.875rem',
            fontWeight: 500,
            '&:hover': { color: 'ink' },
            '&[aria-current="page"]': { color: 'ink', fontWeight: 600 },
          }}
        >
          {item.label}
        </Link>
      ))}
    </Box>
  );
}
