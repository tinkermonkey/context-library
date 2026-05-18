export const DOMAIN_NAMES = ['documents', 'events', 'health', 'location', 'messages', 'music', 'notes', 'people', 'tasks'] as const;
export type DomainName = (typeof DOMAIN_NAMES)[number];

export const domainColors: Record<DomainName, string> = {
  documents: 'rgb(var(--domain-documents))',
  events: 'rgb(var(--domain-events))',
  health: 'rgb(var(--domain-health))',
  location: 'rgb(var(--domain-location))',
  messages: 'rgb(var(--domain-messages))',
  music: 'rgb(var(--domain-music))',
  notes: 'rgb(var(--domain-notes))',
  people: 'rgb(var(--domain-people))',
  tasks: 'rgb(var(--domain-tasks))',
};

export function getDomainColor(domain: string): string {
  return domainColors[domain as DomainName] ?? domainColors.notes;
}

function hexOpacityToDecimal(hex: string): number {
  const num = parseInt(hex, 16);
  return Math.round((num / 255) * 1000) / 1000;
}

/**
 * Returns a domain color with opacity using CSS rgb/opacity syntax.
 *
 * @param domain - The domain name (falls back to 'notes' if unknown)
 * @param opacity - The opacity value. Can be:
 *   - A number between 0 and 1 (e.g., 0.5, 1)
 *   - A 2-character hex string (e.g., '20', '40', 'FF') which is converted to decimal
 *   - Any other string is passed through as-is to CSS
 *
 * @example
 * getDomainColorWithAlpha('notes', 0.5)    // "rgb(var(--domain-notes) / 0.5)"
 * getDomainColorWithAlpha('notes', '20')   // "rgb(var(--domain-notes) / 0.125)"
 * getDomainColorWithAlpha('tasks', '1A')   // "rgb(var(--domain-tasks) / 0.102)"
 */
export function getDomainColorWithAlpha(domain: string, opacity: string | number): string {
  let domainName: DomainName = domain as DomainName;
  if (!(domainName in domainColors)) {
    domainName = 'notes';
  }

  let opacityValue: number | string;
  if (typeof opacity === 'number') {
    opacityValue = opacity;
  } else if (opacity.length === 2 && /^[0-9a-fA-F]{2}$/.test(opacity)) {
    // 2-char hex string (e.g., '20', '1A', 'FF')
    opacityValue = hexOpacityToDecimal(opacity);
  } else {
    // Pass through as-is (for CSS keywords like 'var(...)' or invalid values)
    opacityValue = opacity;
  }

  const variable = `var(--domain-${domainName})`;
  return `rgb(${variable} / ${opacityValue})`;
}
