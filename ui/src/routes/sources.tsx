import { useCallback, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { PageHeader, TabBar, Chip } from '@tinkermonkey/heimdall-ui';
import { FilterDropdown } from '../components/FilterDropdown';
import { useSources } from '../hooks/useSources';
import { useStats } from '../hooks/useStats';
import { useAdapters } from '../hooks/useAdapters';
import { getDomainColor, DOMAIN_NAMES } from '../lib/designTokens';
import { capitalize } from '../utils/formatters';
import type { SourcesPageSearch } from '../router';

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
  const search = useSearch({ from: '/sources' });

  const activeTab = search.tab ?? 'sources';
  const domainFilter = search.domain ?? '';
  const adapterFilter = search.adapter_id ?? '';
  const page = search.page ?? 0;
  const pageSize = search.pageSize ?? 50;

  const updateSearch = useCallback(
    (updates: Partial<SourcesPageSearch>) => {
      navigate({
        to: '/sources',
        search: { ...search, ...updates } as SourcesPageSearch,
      });
    },
    [navigate, search]
  );

  const statsQuery = useStats();
  const adaptersQuery = useAdapters();

  const sourcesQuery = useSources({
    domain: domainFilter || undefined,
    adapter_id: adapterFilter || undefined,
    limit: pageSize,
    offset: page * pageSize,
    sort_by: 'updated_at',
    order: 'desc',
  });

  const totalSources = statsQuery.data?.total_sources ?? 0;
  const sources = sourcesQuery.data?.sources ?? [];
  const totalFiltered = sourcesQuery.data?.total ?? 0;
  const totalPages = Math.ceil(totalFiltered / pageSize);

  const availableAdapters = useMemo(
    () => adaptersQuery.data?.adapters.map((a) => a.adapter_id) ?? [],
    [adaptersQuery.data]
  );

  const handleDomainChange = useCallback(
    (vals: string[]) => updateSearch({ domain: vals[0] ?? '', page: 0 }),
    [updateSearch]
  );

  const handleAdapterChange = useCallback(
    (vals: string[]) => updateSearch({ adapter_id: vals[0] ?? '', page: 0 }),
    [updateSearch]
  );

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Library"
        title="Sources"
        subtitle={`${totalSources.toLocaleString()} ingested sources across all adapters`}
      />

      {/* ── Tab Bar ── */}
      <div
        className="px-6 pt-4 shrink-0"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        <TabBar
          tabs={[
            { id: 'sources', label: 'Sources', count: totalSources > 0 ? totalSources : undefined },
            { id: 'chunks', label: 'Chunks' },
            { id: 'versions', label: 'Versions' },
            { id: 'retired', label: 'Retired' },
          ]}
          activeTabId={activeTab}
          onSelectTab={(tabId) => updateSearch({ tab: tabId as SourcesPageSearch['tab'], page: 0 })}
        />
      </div>

      {/* ── Filter Bar ── */}
      <div
        className="flex items-center gap-3 px-6 py-3 shrink-0"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        <FilterDropdown
          mode="radio"
          value={domainFilter ? [domainFilter] : []}
          onChange={handleDomainChange}
        >
          <FilterDropdown.Trigger
            label="Domain"
            summary={domainFilter ? capitalize(domainFilter) : 'All'}
          />
          <FilterDropdown.Panel>
            <FilterDropdown.Section>
              <FilterDropdown.Radio value="" label="All Domains" />
              {DOMAIN_NAMES.map((d) => (
                <FilterDropdown.Radio key={d} value={d} label={capitalize(d)} />
              ))}
            </FilterDropdown.Section>
          </FilterDropdown.Panel>
        </FilterDropdown>

        <FilterDropdown
          mode="radio"
          value={adapterFilter ? [adapterFilter] : []}
          onChange={handleAdapterChange}
        >
          <FilterDropdown.Trigger
            label="Adapter"
            summary={adapterFilter || 'All'}
          />
          <FilterDropdown.Panel>
            <FilterDropdown.Section>
              <FilterDropdown.Radio value="" label="All Adapters" />
              {availableAdapters.map((id) => (
                <FilterDropdown.Radio key={id} value={id} label={id} />
              ))}
            </FilterDropdown.Section>
          </FilterDropdown.Panel>
        </FilterDropdown>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'sources' ? (
          sourcesQuery.isLoading ? (
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
                  <th className="p-0" style={{ width: 4 }} />
                  {['Source ID', 'Domain', 'Adapter', 'Version', 'Chunks', 'Last Fetched', 'State'].map((col) => (
                    <th
                      key={col}
                      className="px-4 py-2 text-left font-medium"
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
                  return (
                    <tr
                      key={source.source_id}
                      className="cursor-pointer transition-colors"
                      style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
                      onClick={() => navigate({ to: '/sources/$sourceId', params: { sourceId: source.source_id } })}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgb(var(--canvas-surface))'; }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; }}
                    >
                      {/* domain color bar */}
                      <td className="p-0" style={{ width: 4, background: color }} />

                      {/* source ID */}
                      <td className="px-4 py-3">
                        <code className="text-xs" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
                          {source.source_id.substring(0, 16)}…
                        </code>
                      </td>

                      {/* domain with dot */}
                      <td className="px-4 py-3">
                        <span className="flex items-center gap-1.5">
                          <span
                            className="rounded-full shrink-0"
                            style={{ width: 8, height: 8, background: color, display: 'inline-block' }}
                          />
                          <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                            {capitalize(source.domain)}
                          </span>
                        </span>
                      </td>

                      {/* adapter chip */}
                      <td className="px-4 py-3">
                        <Chip className="text-xs">{source.adapter_id}</Chip>
                      </td>

                      {/* version pill */}
                      <td className="px-4 py-3">
                        <span
                          className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                          style={{
                            background: 'rgb(var(--canvas-surface))',
                            color: 'rgb(var(--canvas-fg-2))',
                            border: `1px solid rgb(var(--canvas-border))`,
                          }}
                        >
                          v{source.current_version}
                        </span>
                      </td>

                      {/* chunk count */}
                      <td className="px-4 py-3">
                        <span className="text-xs font-mono" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                          {source.chunk_count.toLocaleString()}
                        </span>
                      </td>

                      {/* last fetched */}
                      <td className="px-4 py-3">
                        <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                          {timeAgo(source.last_fetched_at)}
                        </span>
                      </td>

                      {/* state chip */}
                      <td className="px-4 py-3">
                        <Chip
                          className="text-xs"
                          style={{
                            color: source.poll_strategy === 'push'
                              ? 'rgb(var(--status-success))'
                              : 'rgb(var(--canvas-fg-2))',
                            background: source.poll_strategy === 'push'
                              ? 'rgb(var(--status-success) / 0.12)'
                              : 'rgb(var(--canvas-surface))',
                            border: 'none',
                          }}
                        >
                          {source.poll_strategy}
                        </Chip>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )
        ) : (
          <div className="flex items-center justify-center py-16">
            <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              {activeTab === 'chunks'
                ? 'Chunks browser coming soon'
                : activeTab === 'versions'
                  ? 'Versions browser coming soon'
                  : 'Retired sources coming soon'}
            </span>
          </div>
        )}
      </div>

      {/* ── Pagination ── */}
      {activeTab === 'sources' && totalPages > 1 && (
        <div
          className="flex items-center justify-between px-6 py-3 shrink-0"
          style={{ borderTop: `1px solid rgb(var(--canvas-border))` }}
        >
          <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            {totalFiltered.toLocaleString()} sources · page {page + 1} of {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => updateSearch({ page: Math.max(0, page - 1) })}
              disabled={page === 0}
              className="px-3 py-1 rounded text-xs transition-colors disabled:opacity-40"
              style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-2))' }}
            >
              Previous
            </button>
            <button
              onClick={() => updateSearch({ page: Math.min(totalPages - 1, page + 1) })}
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
