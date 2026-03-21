import type { ReactNode } from 'react';

interface DomainBadgeProps {
  /** Domain name (e.g., "messages", "health", "tasks") */
  domain: string;
}

/**
 * Color-coded badge for domain names.
 * Provides consistent visual identification across all views.
 *
 * @example
 * <DomainBadge domain="messages" />
 */
export function DomainBadge({ domain }: DomainBadgeProps): ReactNode {
  // Map domains to Tailwind color classes
  const colorMap: Record<string, { bg: string; text: string }> = {
    messages: { bg: 'bg-blue-100', text: 'text-blue-800' },
    notes: { bg: 'bg-purple-100', text: 'text-purple-800' },
    events: { bg: 'bg-green-100', text: 'text-green-800' },
    tasks: { bg: 'bg-orange-100', text: 'text-orange-800' },
    health: { bg: 'bg-red-100', text: 'text-red-800' },
    documents: { bg: 'bg-cyan-100', text: 'text-cyan-800' },
  };

  const colors = colorMap[domain] || { bg: 'bg-gray-100', text: 'text-gray-800' };

  return (
    <span className={`inline-block px-2 py-1 rounded text-xs font-semibold ${colors.bg} ${colors.text}`}>
      {domain}
    </span>
  );
}
