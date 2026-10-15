import { describeCompany } from './describeCompany';

describe('describeCompany', () => {
  it.each([
    ['Telecom Services', 'Mexico', 'Telecom services, headquartered in Mexico'],
    [
      'Consumer Electronics',
      'United States',
      'Consumer electronics, headquartered in the United States',
    ],
    ['Banks - Regional', 'Singapore', 'Regional banks, headquartered in Singapore'],
    ['Drug Manufacturers - General', null, 'Drug manufacturers'],
    ['Software - Infrastructure', null, 'Infrastructure software'],
    ['REIT - Retail', null, 'Retail REITs'],
    ['Information Technology Services', null, 'Information technology services'],
    ['Insurance - Reinsurance', null, 'Reinsurers'],
    ['Beverages - Brewers', null, 'Brewers'],
    ['Beverages - Wineries & Distilleries', null, 'Wineries & distilleries'],
    ['Utilities - Independent Power Producers', null, 'Independent power producers'],
    ['Real Estate - Development', null, 'Real estate development'],
    ['Oil & Gas E&P', null, 'Oil & gas E&P'],
  ])('describes %s in %s', (industry, country, expected) => {
    expect(describeCompany(industry, country)).toBe(expected);
  });

  it('handles a lone industry or a lone country', () => {
    expect(describeCompany('Telecom Services', null)).toBe('Telecom services');
    expect(describeCompany(null, 'Mexico')).toBe('Headquartered in Mexico');
  });

  it('returns an empty string when neither is known', () => {
    expect(describeCompany(null, undefined)).toBe('');
    expect(describeCompany('  ', '')).toBe('');
  });

  it.each([
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
  ])('uses "the" for %s', (country) => {
    expect(describeCompany(null, country)).toBe(`Headquartered in the ${country}`);
  });

  it('keeps acronyms upper-case and only pluralises REIT', () => {
    expect(describeCompany('Software - Application', null)).toBe('Application software');
    expect(describeCompany('ETF', null)).toBe('ETF');
    expect(describeCompany('IT Services', null)).toBe('IT services');
    expect(describeCompany('REIT - Diversified', null)).toBe('Diversified REITs');
  });
});
