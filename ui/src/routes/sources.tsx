import { useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { PageHeader, Chip } from '@tinkermonkey/heimdall-ui';
import { useSources } from '../hooks/useSources';
import { useStats } from '../hooks/useStats';
import { getDomainColor, getDomainColorWithAlpha } from '../lib/designTokens';

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return 'Never';
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 5) return 'just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function SourcesPage(): ReactNode {
  const navigate = useNavigate();
  const [domainFilter, setDomainFilter] = useState<string>('');
  const [page, setPage] = useState(0);
  const pageSize = 50;

  const sourcesQuery = useSources({
    domain: domainFilter || undefined,
    limit: pageSize,
    offset: page * pageSize,
    sort_by: 'updated_at',
    order: 'desc',
  });

  const statsQuery = useStats();
  const domains = statsQuery.data?.by_domain ?? [];
  const totalSources = sourcesQuery.data?.total ?? 0;
  const sources = sourcesQuery.data?.sources ?? [];

  const totalPages = Math.ceil(totalSources / pageSize);

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Library"
        title="Sources"
        subtitle="All ingested content sources across adapters"
      />

      {/* ── Filter bar ── */}
      <div
        className="flex items-center gap-2 px-6 py-3 shrink-0 flex-wrap"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        <button
          onClick={() => { setDomainFilter(''); setPage(0); }}
          className="px-3 py-1 rounded-full text-xs font-medium transition-colors"
          style={{
            background: !domainFilter ? 'rgb(var(--accent-primary) / 0.15)' : 'transparent',
            color: !domainFilter ? 'rgb(var(--accent-primary))' : 'rgb(var(--canvas-fg-3))',
            border: `1px solid ${!domainFilter ? 'rgb(var(--accent-primary) / 0.4)' : 'rgb(var(--canvas-border))'}`,
          }}
        >
          All
        </button>
        {domains.map((d) => {
          const color = getDomainColor(d.domain);
          const isActive = domainFilter === d.domain;
          return (
            <button
              key={d.domain}
              onClick={() => { setDomainFilter(d.domain); setPage(0); }}
              className="px-3 py-1 rounded-full text-xs font-medium transition-colors"
              style={{
                background: isActive ? getDomainColorWithAlpha(d.domain, '26') : 'transparent',
                color: isActive ? color : 'rgb(var(--canvas-fg-3))',
                border: `1px solid ${isActive ? color + '66' : 'rgb(var(--canvas-border))'}`,
              }}
            >
              {capitalize(d.domain)} · {d.source_count}
            </button>
          );
        })}
      </div>

      {/* ── Table ── */}
      <div className="flex-1 overflow-y-auto">
        {sourcesQuery.isLoading ? (
          <div className="flex items-center justify-center py-16">
            <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Loading…</span>
          </div>
        ) : sourcesQuery.isError ? (
          <div className="flex items-center justify-center py-16">
            <span className="text-sm" style={{ color: 'rgb(var(--status-error))' }}>Failed to load sources</span>
          </div>
        ) : sources.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>No sources found</span>
          </div>
        ) : (
          <table className="w-full text-sm" style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}>
                {['Domain', 'Adapter', 'Source', 'Chunks', 'Updated'].map((col) => (
                  <th
                    key={col}
                    className="px-6 py-2 text-left font-medium"
                    style={{ color: 'rgb(var(--canvas-fg-3))', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em' }}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => {
                const color = getDomainColor(source.domain);
                const displayName = source.display_name || source.origin_ref;
                return (
                  <tr
                    key={source.source_id}
                    className="cursor-pointer transition-colors"
                    style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
                    onClick={() => navigate({ to: '/browser', search: { source_id: source.source_id } })}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgb(var(--canvas-surface))'; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; }}
                  >
                    <td className="px-6 py-3">
                      <Chip
                        className="text-xs font-medium"
                        style={{ color, background: getDomainColorWithAlpha(source.domain, '20'), border: 'none' }}
                      >
                        {capitalize(source.domain)}
                      </Chip>
                    </td>
                    <td className="px-6 py-3">
                      <span className="text-xs font-mono" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                        {source.adapter_id}
                      </span>
                    </td>
                    <td className="px-6 py-3 max-w-xs">
                      <span
                        className="text-xs truncate block"
                        style={{ color: 'rgb(var(--canvas-fg-1))' }}
                        title={displayName}
                      >
                        {displayName}
                      </span>
                    </td>
                    <td className="px-6 py-3">
                      <span className="text-xs font-mono" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                        {source.chunk_count.toLocaleString()}
                      </span>
                    </td>
                    <td className="px-6 py-3">
                      <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                        {timeAgo(source.updated_at)}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div
          className="flex items-center justify-between px-6 py-3 shrink-0"
          style={{ borderTop: `1px solid rgb(var(--canvas-border))` }}
        >
          <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            {totalSources.toLocaleString()} sources · page {page + 1} of {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1 rounded text-xs transition-colors disabled:opacity-40"
              style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-2))' }}
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1 rounded text-xs transition-colors disabled:opacity-40"
              style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-2))' }}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
