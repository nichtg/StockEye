import { describeIndustry } from './describeIndustry';

describe('describeIndustry', () => {
  it.each([
    ['Telecom Services', 'Telecom services'],
    ['Consumer Electronics', 'Consumer electronics'],
    ['Banks - Regional', 'Regional banks'],
    ['Drug Manufacturers - General', 'Drug manufacturers'],
    ['Software - Infrastructure', 'Infrastructure software'],
    ['REIT - Retail', 'Retail REITs'],
    ['Information Technology Services', 'Information technology services'],
    ['Insurance - Reinsurance', 'Reinsurers'],
    ['Beverages - Brewers', 'Brewers'],
    ['Beverages - Wineries & Distilleries', 'Wineries & distilleries'],
    ['Utilities - Independent Power Producers', 'Independent power producers'],
    ['Real Estate - Development', 'Real estate development'],
    ['Oil & Gas E&P', 'Oil & gas E&P'],
  ])('describes %s as %s', (industry, expected) => {
    expect(describeIndustry(industry)).toBe(expected);
  });

  it('returns an empty string when the industry is missing or blank', () => {
    expect(describeIndustry(null)).toBe('');
    expect(describeIndustry(undefined)).toBe('');
    expect(describeIndustry('  ')).toBe('');
  });

  it('keeps acronyms upper-case and only pluralises REIT', () => {
    expect(describeIndustry('Software - Application')).toBe('Application software');
    expect(describeIndustry('ETF')).toBe('ETF');
    expect(describeIndustry('IT Services')).toBe('IT services');
    expect(describeIndustry('REIT - Diversified')).toBe('Diversified REITs');
  });
});
