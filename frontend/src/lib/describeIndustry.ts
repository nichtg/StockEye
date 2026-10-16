/** Words kept upper-case when the rest of an industry name is lowercased. */
const ACRONYMS = new Set(['ETF', 'IT', 'US', 'REIT', 'REITs', 'E&P']);

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
 * The industry as a sentence-case label for the stock header chip: "Regional banks", "Retail REITs".
 * Returns '' when the industry is missing.
 */
export function describeIndustry(industry: string | null | undefined): string {
  const ind = clean(industry);
  if (!ind) return '';
  const phrase = industryPhrase(ind);
  return phrase.charAt(0).toUpperCase() + phrase.slice(1);
}
