import { describe, it, expect } from 'vitest';
import { getDomainColor, domainColors } from './designTokens';

describe('getDomainColor', () => {
  it('returns the correct color for each defined domain', () => {
    const domains = Object.keys(domainColors);

    domains.forEach((domain) => {
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
      expect(result).toContain(')\)');
    });
  });

  it('returns CSS variable reference format', () => {
    const color = getDomainColor('notes');
    expect(color).toBe('rgb(var(--domain-notes))');
    expect(color).toMatch(/^rgb\(var\(--domain-\w+\)\)$/);
  });
});
