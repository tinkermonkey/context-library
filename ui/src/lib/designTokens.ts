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

export function getDomainColorWithAlpha(domain: string, opacity: string | number): string {
  let domainName: DomainName = domain as DomainName;
  if (!(domainName in domainColors)) {
    domainName = 'notes';
  }

  let opacityValue: number | string;
  if (typeof opacity === 'number') {
    opacityValue = opacity;
  } else if (opacity.length === 2) {
    opacityValue = hexOpacityToDecimal(opacity);
  } else {
    opacityValue = opacity;
  }

  const variable = `var(--domain-${domainName})`;
  return `rgb(${variable} / ${opacityValue})`;
}
