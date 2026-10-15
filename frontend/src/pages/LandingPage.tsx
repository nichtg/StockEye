import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import { styled } from '@mui/material/styles';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import { useEffect } from 'react';
import { Link as RouterLink } from 'react-router';
import homeDark from '../assets/landing/home-dark.webp';
import homeLight from '../assets/landing/home-light.webp';
import macroLight from '../assets/landing/macro-light.webp';
import stockDark from '../assets/landing/stock-dark.webp';
import stockLight from '../assets/landing/stock-light.webp';
import { SiteFooter } from '../components/SiteFooter';
import { ThemeToggle } from '../components/ThemeToggle';
import { Wordmark } from '../components/Wordmark';
import { useColorMode } from '../theme/colorModeContext';
import { layout, radius } from '../theme/tokens';

const MAIN_ID = 'main-content';
const gutter = { xs: 2, md: 3 };

interface Feature {
  title: string;
  body: string;
  alt: string;
  light: string;
  dark: string;
  width: number;
  height: number;
}

const features: Feature[] = [
  {
    title: 'The week ahead, in one line',
    body: 'The Technical tab sums up the short-term lean as bullish, neutral or bearish. Candlestick patterns and indicators sit underneath, each explained in plain words, on a chart you can move and zoom.',
    alt: 'A StockEye stock page: a candlestick chart for Apple with earnings and dividend markers, and a short-term lean of bullish with the signals behind it.',
    light: stockLight,
    dark: stockDark,
    width: 1440,
    height: 1100,
  },
  {
    title: 'What the news really did',
    body: 'The Macro tab compares every news day with what the market alone would have predicted, over two years. You see whether the news moved the price or whether it was just the market. The News tab lists the latest articles.',
    alt: 'The Macro tab for DBS Group: plain sentences on what the news did to the price, and a weekly sentiment chart.',
    light: macroLight,
    dark: macroLight,
    width: 1440,
    height: 1020,
  },
  {
    title: 'Find stocks people overlook',
    body: 'Discover brings you nightly lists of smaller US and Singapore companies. Keep the ones you like on your watchlist, and sort it by country.',
    alt: 'A StockEye watchlist: a table of stocks with last price, one-week change, a small trend line and an outlook.',
    light: homeLight,
    dark: homeDark,
    width: 1440,
    height: 900,
  },
];

// A styled <img> keeps width and height as real attributes (a Box would read them as style props),
// so the browser reserves the space before the image loads.
const Screenshot = styled('img')(({ theme }) => ({
  display: 'block',
  width: '100%',
  height: 'auto',
  border: `1px solid ${theme.palette.line}`,
  borderRadius: radius.lg,
}));

function FeatureImage({ feature, lazy }: { feature: Feature; lazy: boolean }) {
  const { mode } = useColorMode();
  return (
    <Screenshot
      src={mode === 'dark' ? feature.dark : feature.light}
      alt={feature.alt}
      width={feature.width}
      height={feature.height}
      loading={lazy ? 'lazy' : undefined}
      decoding="async"
    />
  );
}

function CreateAccount() {
  return (
    <Button
      component={RouterLink}
      to="/register"
      variant="contained"
      size="large"
      sx={{ width: { xs: '100%', sm: 'auto' } }}
    >
      Create a free account
    </Button>
  );
}

export default function LandingPage() {
  useEffect(() => {
    document.title = 'StockEye – plain-English stock analysis';
    return () => {
      document.title = 'StockEye';
    };
  }, []);

  return (
    <Box sx={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column' }}>
      <Box
        component="a"
        href={`#${MAIN_ID}`}
        sx={{
          position: 'absolute',
          left: 16,
          top: -100,
          zIndex: (t) => t.zIndex.tooltip + 1,
          bgcolor: 'ink',
          color: 'bg',
          px: 2,
          py: 1,
          borderRadius: 1,
          '&:focus-visible': { top: 8, outlineColor: 'var(--mui-palette-bg)' },
        }}
      >
        Skip to content
      </Box>
      <AppBar
        position="sticky"
        color="inherit"
        elevation={0}
        sx={{ bgcolor: 'bg', borderBottom: 1, borderColor: 'line', backgroundImage: 'none' }}
      >
        <Toolbar
          disableGutters
          sx={{
            minHeight: layout.topBarHeight,
            px: gutter,
            gap: 1,
            maxWidth: layout.columnWidth,
            width: '100%',
            mx: 'auto',
          }}
        >
          <Wordmark />
          <Box sx={{ flex: 1 }} />
          <ThemeToggle />
          <Button component={RouterLink} to="/login" color="inherit">
            Sign in
          </Button>
        </Toolbar>
      </AppBar>

      <Box
        component="main"
        id={MAIN_ID}
        tabIndex={-1}
        sx={{
          flex: 1,
          width: '100%',
          maxWidth: layout.columnWidth,
          mx: 'auto',
          px: gutter,
          outline: 'none',
        }}
      >
        <Box sx={{ pt: { xs: 6, md: 10 }, pb: { xs: 6, md: 8 }, maxWidth: 720 }}>
          <Typography
            variant="h1"
            sx={{
              fontSize: { xs: '2rem', md: '2.5rem' },
              lineHeight: 1.15,
              letterSpacing: '-0.02em',
            }}
          >
            See what moves your stocks
          </Typography>
          <Typography sx={{ color: 'ink2', mt: 2, fontSize: '1.0625rem' }}>
            StockEye reads the news and the chart for US and Singapore stocks, and tells you in
            plain words what it found: how news has moved the price over two years, and where the
            chart leans this week.
          </Typography>
          <Box
            sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 1.5, mt: 4 }}
          >
            <CreateAccount />
            <Button
              component={RouterLink}
              to="/login"
              variant="outlined"
              color="inherit"
              size="large"
              sx={{ width: { xs: '100%', sm: 'auto' } }}
            >
              Sign in
            </Button>
          </Box>
          <Typography variant="body2" sx={{ color: 'ink3', mt: 2 }}>
            Free. No card needed. Analysis only, not investment advice.
          </Typography>
        </Box>

        {features.map((f, i) => (
          <Box
            key={f.title}
            component="section"
            sx={{
              borderTop: 1,
              borderColor: 'line',
              py: { xs: 6, md: 8 },
              display: 'flex',
              flexDirection: { xs: 'column', md: i % 2 === 0 ? 'row' : 'row-reverse' },
              alignItems: { md: 'center' },
              gap: { xs: 3, md: 6 },
            }}
          >
            <Box sx={{ flex: { md: '0 0 340px' } }}>
              <Typography variant="h2" sx={{ fontSize: '1.375rem' }}>
                {f.title}
              </Typography>
              <Typography sx={{ color: 'ink2', mt: 1.5 }}>{f.body}</Typography>
            </Box>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <FeatureImage feature={f} lazy={i > 0} />
            </Box>
          </Box>
        ))}

        <Box sx={{ borderTop: 1, borderColor: 'line', py: { xs: 6, md: 8 } }}>
          <Typography variant="h2" sx={{ fontSize: '1.375rem', mb: 3 }}>
            Start with one stock
          </Typography>
          <CreateAccount />
        </Box>
      </Box>

      <SiteFooter />
    </Box>
  );
}
