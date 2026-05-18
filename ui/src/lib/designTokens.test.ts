import { describe, it, expect } from 'vitest';
import { getDomainColor, getDomainColorWithAlpha, domainColors, DOMAIN_NAMES } from './designTokens';

describe('getDomainColor', () => {
  it('returns the correct color for each defined domain', () => {
    DOMAIN_NAMES.forEach((domain) => {
      expect(getDomainColor(domain)).toBe(domainColors[domain]);
    });
  });

  it('returns the notes color as default for unknown domains', () => {
    expect(getDomainColor('unknown')).toBe(domainColors.notes);
    expect(getDomainColor('foobar')).toBe(domainColors.notes);
    expect(getDomainColor('invalid-domain')).toBe(domainColors.notes);
  });

  it('returns the notes color for empty string', () => {
    expect(getDomainColor('')).toBe(domainColors.notes);
  });

  it('handles all documented domains', () => {
    const expectedDomains = [
      'documents',
      'events',
      'health',
      'location',
      'messages',
      'music',
      'notes',
      'people',
      'tasks',
    ];

    expectedDomains.forEach((domain) => {
      const result = getDomainColor(domain);
      expect(result).toMatch(/^rgb\(var\(--domain-/);
      expect(result).toContain(domain);
      expect(result).toContain('))');
    });
  });

  it('returns CSS variable reference format', () => {
    const color = getDomainColor('notes');
    expect(color).toBe('rgb(var(--domain-notes))');
    expect(color).toMatch(/^rgb\(var\(--domain-\w+\)\)$/);
  });
});

describe('getDomainColorWithAlpha', () => {
  it('converts 2-character hex opacity to decimal', () => {
    const result = getDomainColorWithAlpha('notes', '20');
    expect(result).toBe('rgb(var(--domain-notes) / 0.125)');
  });

  it('converts common hex opacity values correctly', () => {
    expect(getDomainColorWithAlpha('notes', '1A')).toBe('rgb(var(--domain-notes) / 0.102)');
    expect(getDomainColorWithAlpha('notes', '26')).toBe('rgb(var(--domain-notes) / 0.149)');
    expect(getDomainColorWithAlpha('notes', '40')).toBe('rgb(var(--domain-notes) / 0.251)');
  });

  it('accepts numeric opacity and passes through directly', () => {
    const result = getDomainColorWithAlpha('notes', 0.5);
    expect(result).toBe('rgb(var(--domain-notes) / 0.5)');
  });

  it('accepts numeric opacity as integer', () => {
    const result = getDomainColorWithAlpha('notes', 1);
    expect(result).toBe('rgb(var(--domain-notes) / 1)');
  });

  it('accepts numeric opacity as zero', () => {
    const result = getDomainColorWithAlpha('notes', 0);
    expect(result).toBe('rgb(var(--domain-notes) / 0)');
  });

  it('falls back to notes domain for unknown domains', () => {
    expect(getDomainColorWithAlpha('unknown', '20')).toBe('rgb(var(--domain-notes) / 0.125)');
    expect(getDomainColorWithAlpha('invalid', 0.5)).toBe('rgb(var(--domain-notes) / 0.5)');
  });

  it('returns valid CSS rgb format with opacity', () => {
    const result = getDomainColorWithAlpha('events', '80');
    expect(result).toMatch(/^rgb\(var\(--domain-\w+\) \/ [\d.]+\)$/);
  });

  it('works with all defined domains', () => {
    DOMAIN_NAMES.forEach((domain) => {
      const result = getDomainColorWithAlpha(domain, '20');
      expect(result).toContain(`var(--domain-${domain})`);
      expect(result).toMatch(/^rgb\(var\(--domain-\w+\) \/ [\d.]+\)$/);
    });
  });
});
