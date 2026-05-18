/* Domain accent colors registered as Heimdall CSS custom properties */
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

/* Semantic color tokens mapped to Heimdall design system */
export const colors = {
  /* Foreground / Text colors */
  textPrimary: 'rgb(var(--canvas-fg-1))',
  textSecondary: 'rgb(var(--canvas-fg-2))',
  textTertiary: 'rgb(var(--canvas-fg-3))',
  textMuted: 'rgb(var(--canvas-fg-4))',

  /* Background colors */
  bgPrimary: 'rgb(var(--canvas-bg))',
  bgSecondary: 'rgb(var(--canvas-bg-2))',
  surface: 'rgb(var(--canvas-surface))',
  card: 'rgb(var(--canvas-card))',

  /* Border colors */
  border: 'rgb(var(--canvas-border))',
  borderStrong: 'rgb(var(--canvas-border-strong))',

  /* Status colors */
  statusOk: 'rgb(var(--status-ok))',
  statusError: 'rgb(var(--status-error))',
  statusWarn: 'rgb(var(--status-warn))',

  /* Accent colors */
  accentPrimary: 'rgb(var(--accent-primary))',
  accentPrimaryHover: 'rgb(var(--accent-primary-hover))',
  accentPrimaryDeep: 'rgb(var(--accent-primary-deep))',
};
