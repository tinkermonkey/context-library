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
  return domainColors[domain] ?? '#6366F1';
}
