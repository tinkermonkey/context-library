export const colors = {
  // Text
  textPrimary: '#F1F5F9',
  textMuted: '#94A3B8',
  textDim: '#64748B',

  // Backgrounds
  bgSurface: '#1E293B',
  bgElevated: '#334155',

  // Borders & accents
  border: '#334155',
  accent: '#6366F1',

  // Status
  statusGreen: '#22C55E',
  statusRed: '#EF4444',
};

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
  return domainColors[domain] ?? colors.accent;
}
