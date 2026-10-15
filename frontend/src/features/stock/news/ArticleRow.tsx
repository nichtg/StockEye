import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Typography from '@mui/material/Typography';
import { useId, useState } from 'react';
import type { NewsArticle } from '../../../api/types';
import type { Exchange } from '../../../lib/exchange';
import { formatClock } from '../../../lib/format';

const SENTIMENT_LABEL: Record<NewsArticle['sentiment_label'], string> = {
  positive: 'Positive',
  negative: 'Negative',
  neutral: 'Neutral',
  not_scored: 'Not scored yet',
};

function SentimentBadge({ label }: { label: NewsArticle['sentiment_label'] }) {
  return (
    <Chip
      label={SENTIMENT_LABEL[label]}
      size="small"
      variant="outlined"
      sx={{
        height: 20,
        flexShrink: 0,
        color: label === 'not_scored' ? 'ink3' : 'ink2',
        borderColor: 'ink3',
        fontWeight: label === 'neutral' || label === 'not_scored' ? 400 : 500,
      }}
    />
  );
}

function SourceTime({
  source,
  iso,
  exchange,
}: {
  source: string;
  iso: string;
  exchange: Exchange;
}) {
  return (
    <>
      {source}{' '}
      <Box component="span" sx={{ ml: 1 }}>
        {formatClock(iso, exchange)}
      </Box>
    </>
  );
}

/** The "+2 similar stories" button and the list it reveals; the badge above is their average. */
function SimilarStories({
  similar,
  exchange,
}: {
  similar: NewsArticle['similar'];
  exchange: Exchange;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const n = similar.length;
  return (
    <>
      <ButtonBase
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => {
          setOpen((v) => !v);
        }}
        sx={{
          display: 'block',
          minHeight: 24,
          mt: 0.5,
          fontSize: '0.8125rem',
          fontWeight: 500,
          color: 'ink2',
          textDecoration: 'underline',
          borderRadius: 0.5,
          '&:hover': { color: 'ink' },
        }}
      >
        {`+${String(n)} similar ${n === 1 ? 'story' : 'stories'}`}
      </ButtonBase>
      <Box
        component="ul"
        id={listId}
        hidden={!open}
        sx={{ listStyle: 'none', m: 0, mt: 0.5, p: 0, pl: 2, color: 'ink2' }}
      >
        {similar.map((s, i) => (
          <Box component="li" key={`${s.url}|${String(i)}`} sx={{ py: 0.5 }}>
            <Link
              href={s.url}
              target="_blank"
              rel="noopener noreferrer"
              sx={{ overflowWrap: 'anywhere', color: 'ink2' }}
            >
              {s.title}
            </Link>
            <Typography variant="body2" sx={{ color: 'ink3' }}>
              <SourceTime source={s.source} iso={s.published_at} exchange={exchange} />
            </Typography>
          </Box>
        ))}
      </Box>
    </>
  );
}

export function ArticleRow({ article, exchange }: { article: NewsArticle; exchange: Exchange }) {
  return (
    <Box
      component="li"
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        alignItems: { sm: 'flex-start' },
        justifyContent: 'space-between',
        gap: { xs: 0.75, sm: 2 },
        py: 1.5,
        borderBottom: 1,
        borderColor: 'line',
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Link
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          sx={{ overflowWrap: 'anywhere' }}
        >
          {article.title}
        </Link>
        <Typography variant="body2" sx={{ color: 'ink3' }}>
          <SourceTime source={article.source} iso={article.published_at} exchange={exchange} />
        </Typography>
        {article.similar.length > 0 && (
          <SimilarStories similar={article.similar} exchange={exchange} />
        )}
      </Box>
      <Box sx={{ alignSelf: { xs: 'flex-start', sm: 'auto' } }}>
        <SentimentBadge label={article.sentiment_label} />
      </Box>
    </Box>
  );
}
