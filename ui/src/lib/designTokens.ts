// CSS custom properties for domain colors (registered in src/index.css)
const domainCSSVars: Record<string, string> = {
  documents: 'var(--domain-documents)',
  events: 'var(--domain-events)',
  health: 'var(--domain-health)',
  location: 'var(--domain-location)',
  messages: 'var(--domain-messages)',
  music: 'var(--domain-music)',
  notes: 'var(--domain-notes)',
  people: 'var(--domain-people)',
  tasks: 'var(--domain-tasks)',
};

// Fallback hex values for non-CSS contexts
export const domainColors: Record<string, string> = {
  documents: '#22C55E',
  events: '#F59E0B',
  health: '#06B6D4',
  location: '#14B8A6',
  messages: '#A855F7',
  music: '#F43F5E',
  notes: '#6366F1',
  people: '#EC4899',
  tasks: '#F97316',
};

export function getDomainColor(domain: string): string {
  return domainCSSVars[domain] ?? domainCSSVars.notes;
}

export function getDomainColorHex(domain: string): string {
  return domainColors[domain] ?? domainColors.notes;
}
