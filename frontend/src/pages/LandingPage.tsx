import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import { styled } from '@mui/material/styles';
import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router';
import homeDark from '../assets/landing/home-dark.webp';
import homeLight from '../assets/landing/home-light.webp';
import macroLight from '../assets/landing/macro-light.webp';
import stockDark from '../assets/landing/stock-dark.webp';
import stockLight from '../assets/landing/stock-light.webp';
import { SiteFrame } from '../components/SiteFrame';
import { ThemeToggle } from '../components/ThemeToggle';
import { useDocumentTitle } from '../hooks';
import { useColorMode } from '../theme/colorModeContext';
import { radius } from '../theme/tokens';

interface Shot {
  src: string;
  width: number;
  height: number;
}

interface Feature {
  title: string;
  body: string;
  alt: string;
  light: Shot;
  /** Omitted when there is no dark capture: the light one is shown, dimmed. */
  dark?: Shot;
}

const features: Feature[] = [
  {
    title: 'The week ahead, in one line',
    body: 'The Technical tab sums up the short-term lean as bullish, neutral or bearish. Candlestick patterns and indicators sit underneath, each explained in plain words, on a chart you can move and zoom.',
    alt: 'A StockEye stock page: a candlestick chart for Apple with earnings and dividend markers, and a short-term lean of bullish with the signals behind it.',
    light: { src: stockLight, width: 1440, height: 1100 },
    dark: { src: stockDark, width: 1440, height: 1100 },
  },
  {
    title: 'What the news really did',
    body: 'The Macro tab compares each news day over the past two years with what the market alone would have predicted. You see whether the news moved the price or whether it was just the market. The News tab lists the last six months of articles.',
    alt: 'The Macro tab for DBS Group: plain sentences on what the news did to the price, and a weekly sentiment chart.',
    light: { src: macroLight, width: 1440, height: 1020 },
  },
  {
    title: 'Find smaller companies to look into',
    body: 'Discover brings you nightly lists of smaller US and Singapore companies. Keep the ones you like on your watchlist, and sort it by country.',
    alt: 'A StockEye watchlist: a table of stocks with last price, one-week change, a small trend line and an outlook.',
    light: { src: homeLight, width: 1440, height: 900 },
    dark: { src: homeDark, width: 1440, height: 900 },
  },
];

// A styled <img> keeps width and height as real attributes (a Box would read them as style props),
// so the browser reserves the space before the image loads.
const Screenshot = styled('img', { shouldForwardProp: (p) => p !== 'dimmed' })<{
  dimmed: boolean;
}>(({ theme, dimmed }) => ({
  display: 'block',
  width: '100%',
  height: 'auto',
  border: `1px solid ${theme.palette.line}`,
  borderRadius: radius.lg,
  // A light-only capture would be a white slab on a black page, so tone it down in dark mode.
  ...(dimmed && { filter: 'brightness(0.85)', borderColor: theme.palette.raised }),
}));

function FeatureImage({ feature, lazy }: { feature: Feature; lazy: boolean }) {
  const { mode } = useColorMode();
  const dimmed = mode === 'dark' && !feature.dark;
  const shot = mode === 'dark' && feature.dark ? feature.dark : feature.light;
  return (
    <Screenshot
      src={shot.src}
      alt={feature.alt}
      width={shot.width}
      height={shot.height}
      loading={lazy ? 'lazy' : undefined}
      decoding="async"
      dimmed={dimmed}
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
  useDocumentTitle();

  return (
    <SiteFrame
      mainPaddingY={0}
      actions={
        <>
          <Box sx={{ flex: 1 }} />
          <ThemeToggle />
          <Button component={RouterLink} to="/login" color="inherit">
            Sign in
          </Button>
        </>
      }
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
          StockEye reads the news and the chart for US and Singapore stocks, and tells you in plain
          words what it found: how news has moved the price over two years, and where the chart
          leans this week.
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 1.5, mt: 4 }}>
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
          Free. Analysis only, not investment advice.
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

      <Box
        component="section"
        aria-labelledby="start-heading"
        sx={{ borderTop: 1, borderColor: 'line', py: { xs: 6, md: 8 } }}
      >
        <Typography variant="h2" id="start-heading" sx={{ fontSize: '1.375rem', mb: 3 }}>
          Start with one stock
        </Typography>
        <CreateAccount />
      </Box>
    </SiteFrame>
  );
}
