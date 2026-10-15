/** Words kept upper-case when the rest of an industry name is lowercased. */
const ACRONYMS = new Set(['ETF', 'IT', 'US', 'REIT', 'REITs', 'E&P']);

/** Countries whose name reads naturally with "the" ("headquartered in the Netherlands"). */
const COUNTRIES_WITH_ARTICLE = new Set([
  'United States',
  'United Kingdom',
  'Netherlands',
  'Philippines',
  'United Arab Emirates',
  'Cayman Islands',
  'Marshall Islands',
  'Bahamas',
  'British Virgin Islands',
  'Czech Republic',
]);

/**
 * Industries where the second part is already a full noun, so swapping "X - Y" into "Y X" would
 * read wrongly ("Reinsurance insurance"). Keyed by the lowercase Yahoo name.
 */
const INDUSTRY_OVERRIDES = new Map<string, string>([
  ['insurance - reinsurance', 'reinsurers'],
  ['beverages - brewers', 'brewers'],
  ['beverages - wineries & distilleries', 'wineries & distilleries'],
  ['utilities - independent power producers', 'independent power producers'],
  ['real estate - development', 'real estate development'],
]);

function clean(value: string | null | undefined): string {
  return value?.trim() ?? '';
}

function phraseWord(word: string): string {
  const upper = word.toUpperCase();
  if (upper === 'REITS') return 'REITs';
  return ACRONYMS.has(upper) ? upper : word.toLowerCase();
}

/**
 * Yahoo industry ("Banks - Regional", "REIT - Retail") as a lowercase noun phrase
 * ("regional banks", "retail REITs"). Yahoo lists the general term first and the qualifier
 * second, which reads backwards in English, so the parts are swapped. "General" adds nothing
 * ("Drug Manufacturers - General" is just "drug manufacturers") and is dropped.
 */
function industryPhrase(industry: string): string {
  const override = INDUSTRY_OVERRIDES.get(industry.toLowerCase().replace(/\s+/g, ' '));
  if (override) return override;
  const parts = industry
    .split(/\s+-\s+/)
    .map((p) => p.trim())
    .filter(Boolean)
    .filter((p, i, all) => !(all.length > 1 && i > 0 && p.toLowerCase() === 'general'));
  // Only a REIT is pluralised: "REIT - Retail" means "retail REITs"; the rest stay as Yahoo gives them.
  const ordered = parts.map((p) => (p.toUpperCase() === 'REIT' ? 'REITs' : p)).reverse();
  return ordered.join(' ').split(/\s+/).map(phraseWord).join(' ');
}

/**
 * One plain-English line for the stock header: "Telecom services, headquartered in Mexico".
 * Either input may be missing; returns '' when both are.
 */
export function describeCompany(
  industry: string | null | undefined,
  country: string | null | undefined,
): string {
  const ind = clean(industry);
  const ctry = clean(country);
  const parts: string[] = [];
  if (ind) parts.push(industryPhrase(ind));
  if (ctry) parts.push(`headquartered in ${COUNTRIES_WITH_ARTICLE.has(ctry) ? 'the ' : ''}${ctry}`);
  const line = parts.join(', ');
  return line.charAt(0).toUpperCase() + line.slice(1);
}
