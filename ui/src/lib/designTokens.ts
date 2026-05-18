export const domainColors: Record<string, string> = {
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
  return domainColors[domain] ?? domainColors.notes;
}
