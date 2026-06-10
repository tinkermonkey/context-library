import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useRouterState } from '@tanstack/react-router';
import { Drawer, Panel, PageHeader, ResultCard, SegmentedControl } from '@tinkermonkey/heimdall-ui';
import { FilterDropdown } from '../components/FilterDropdown';
import { FacetList } from '../components/FacetList';
import { SearchHero } from '../components/SearchHero';
import { useSearch } from '../hooks/useSearch';
import { useAdapterStats } from '../hooks/useAdapterStats';
import { useToast } from '../hooks/useToast';
import type { SearchPageSearch } from '../router';
import type { QueryResultItem } from '../types/api';
import { getDomainColor, getDomainColorWithAlpha, domainColors } from '../lib/designTokens';
import { capitalize } from '../utils/formatters';

// ── Constants ─────────────────────────────────────────────────────

const SEARCH_DOMAINS = Object.keys(domainColors);

const SUGGESTED_QUERIES = [
  'What did I read about machine learning last month?',
  'Recent messages from my team',
  'Health trends this week',
  'Open tasks due soon',
  'Notes about architecture decisions',
  'Documents related to my projects',
];

const SORT_OPTIONS = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'date', label: 'Version' },
  { value: 'source', label: 'Source' },
];

// ── Debounce hook ─────────────────────────────────────────────────

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

// ── Helpers ───────────────────────────────────────────────────────

function shortHash(hash: string): string {
  return hash.length > 16 ? `${hash.substring(0, 16)}…` : hash;
}

function highlightSnippet(
  result: QueryResultItem,
  query: string
): React.ReactNode {
  const text = result.context_header
    ? `${result.context_header}\n\n${result.chunk_text}`
    : result.chunk_text;
  const preview = text.substring(0, 300);
  const terms = query
    .split(/\s+/)
    .filter((t) => t.length > 2)
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (terms.length === 0) return <span className="text-xs leading-relaxed whitespace-pre-wrap">{preview}</span>;
  const pattern = new RegExp(`(${terms.join('|')})`, 'gi');
  const parts = preview.split(pattern);
  return (
    <span className="text-xs leading-relaxed whitespace-pre-wrap">
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <mark
            key={i}
            className="rounded px-0.5"
            style={{
              background: getDomainColorWithAlpha(result.domain, '30'),
              color: 'rgb(var(--canvas-fg-1))',
              fontWeight: 500,
            }}
          >
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
      {text.length > 300 ? '…' : ''}
    </span>
  );
}

// ── Detail panel drawer ────────────────────────────────────────────

function DetailDrawer({
  result,
  isOpen,
  onClose,
  onViewInBrowser,
}: {
  result: QueryResultItem | null;
  isOpen: boolean;
  onClose: () => void;
  onViewInBrowser: () => void;
}) {
  const domainColor = result ? getDomainColor(result.domain) : undefined;
  const fullContent = result
    ? result.context_header
      ? `${result.context_header}\n\n${result.chunk_text}`
      : result.chunk_text
    : '';

  return (
    <Drawer isOpen={isOpen} onClose={onClose} position="right" title="Result Detail">
      {result && (
        <div className="flex flex-col gap-5 p-4 overflow-y-auto flex-1">
          <div className="flex flex-col gap-2.5">
            {[
              { label: 'Source', value: result.adapter_id },
              { label: 'Domain', value: capitalize(result.domain), color: domainColor },
              { label: 'Chunk type', value: result.chunk_type },
              { label: 'Score', value: result.similarity_score.toFixed(4) },
              { label: 'Version', value: String(result.source_version_id) },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex items-start justify-between gap-4">
                <span className="text-xs shrink-0" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  {label}
                </span>
                <span className="text-xs font-medium text-right" style={{ color: color ?? 'rgb(var(--canvas-fg-1))' }}>
                  {value}
                </span>
              </div>
            ))}
            <div className="flex flex-col gap-1">
              <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Chunk hash</span>
              <span className="text-[11px] font-mono break-all" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                {result.chunk_hash}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Source ID</span>
              <span className="text-[11px] font-mono break-all" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                {result.source_id}
              </span>
            </div>
          </div>
          <div className="h-px" style={{ background: 'rgb(var(--canvas-border))' }} />
          <div className="flex flex-col gap-2">
            <span className="text-xs font-semibold" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
              Full Content
            </span>
            <p className="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
              {fullContent}
            </p>
          </div>
          <div className="pt-4 border-t" style={{ borderColor: 'rgb(var(--canvas-border))' }}>
            <button
              onClick={onViewInBrowser}
              className="flex items-center gap-1.5 text-xs font-medium"
              style={{ color: domainColor }}
            >
              View in Browser
            </button>
          </div>
        </div>
      )}
    </Drawer>
  );
}

// ── Empty state ───────────────────────────────────────────────────

function EmptyState({ onSelect }: { onSelect: (q: string) => void }) {
  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 56, height: 56, background: 'rgb(var(--accent-primary) / 0.1)' }}
      >
        <span style={{ color: 'rgb(var(--accent-primary))', fontSize: 28 }}>⌕</span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
          Search your knowledge base
        </p>
        <p className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          Semantic search across all ingested content
        </p>
      </div>
      <div className="flex flex-col gap-2 w-full max-w-md">
        <p className="text-xs mb-1 text-center" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          Try asking…
        </p>
        {SUGGESTED_QUERIES.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            className="flex items-center gap-2.5 px-4 py-2.5 rounded-lg text-left transition-colors"
            style={{
              background: 'rgb(var(--canvas-surface))',
              border: '1px solid rgb(var(--canvas-border))',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = 'rgb(var(--accent-primary))';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = 'rgb(var(--canvas-border))';
            }}
          >
            <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-2))' }}>{q}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Skeleton card ─────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-3"
      style={{ background: 'rgb(var(--canvas-surface))', border: '1px solid rgb(var(--canvas-border))' }}
    >
      <div className="flex items-center gap-2">
        <div className="w-16 h-5 rounded-full animate-pulse" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
        <div className="flex-1 h-3 rounded animate-pulse" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
        <div className="w-16 h-3 rounded animate-pulse" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="h-3 rounded animate-pulse w-full" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
        <div className="h-3 rounded animate-pulse w-4/5" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
        <div className="h-3 rounded animate-pulse w-3/5" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
      </div>
    </div>
  );
}

// ── Search page ───────────────────────────────────────────────────

export default function SearchPage() {
  const navigate = useNavigate();
  const routerState = useRouterState();
  const search = (routerState.location.search ?? {}) as SearchPageSearch;
  const { showToast } = useToast();

  const searchRef = useRef(search);
  const prevSearchRef = useRef(search);

  // Local input value — debounced to URL
  const [inputValue, setInputValue] = useState(search.q ?? '');
  // Client-side filter state
  const [domainFilter, setDomainFilter] = useState<string[]>(search.domain ? [search.domain] : []);
  const [adapterFilter, setAdapterFilter] = useState<string[]>([]);
  const [minScore, setMinScore] = useState<string>('any');
  const [sortOrder, setSortOrder] = useState<string | number>('relevance');
  // Selected result for detail panel
  const [selectedResult, setSelectedResult] = useState<QueryResultItem | null>(null);

  const adapterStats = useAdapterStats();
  const availableAdapters = useMemo(
    () => adapterStats.data?.adapters.map((a) => a.adapter_id) ?? [],
    [adapterStats.data]
  );

  // Sync input if URL changes externally
  useEffect(() => {
    if (search.q !== prevSearchRef.current.q) {
      setInputValue(search.q ?? '');
    }
    if (search.domain !== prevSearchRef.current.domain) {
      setDomainFilter(search.domain ? [search.domain] : []);
    }
    prevSearchRef.current = search;
  }, [search]);

  useEffect(() => {
    searchRef.current = search;
  }, [search]);

  // Debounce + URL sync
  const debouncedQuery = useDebounce(inputValue, 300);
  useEffect(() => {
    if (debouncedQuery === (searchRef.current.q ?? '')) return;
    navigate({
      to: '/search',
      search: { ...searchRef.current, q: debouncedQuery || undefined },
    });
  }, [debouncedQuery, navigate]);

  // Domain filter → also sync to URL (single value; use first selected)
  const handleDomainFilterChange = useCallback(
    (values: string[]) => {
      setDomainFilter(values);
      setSelectedResult(null);
      const domain = values.length === 1 ? values[0] : undefined;
      navigate({
        to: '/search',
        search: { ...searchRef.current, q: inputValue || undefined, domain },
      });
    },
    [navigate, inputValue]
  );

  const { data, isLoading, error } = useSearch(search);
  const allResults = data?.results ?? [];

  // Toast on error
  useEffect(() => {
    if (error) {
      showToast({
        title: 'Search failed',
        subtitle: error instanceof Error ? error.message : 'Unknown error',
        variant: 'error',
        duration: 4000,
      });
    }
  }, [error, showToast]);

  // Apply client-side filters
  const filteredResults = useMemo(() => {
    let results = allResults;
    if (adapterFilter.length > 0) {
      results = results.filter((r) => adapterFilter.includes(r.adapter_id));
    }
    if (minScore !== 'any') {
      const thresholds: Record<string, number> = { high: 0.8, medium: 0.6, low: 0.4 };
      const threshold = thresholds[minScore] ?? 0;
      results = results.filter((r) => r.similarity_score >= threshold);
    }
    return results;
  }, [allResults, adapterFilter, minScore]);

  // Apply sort
  const sortedResults = useMemo(() => {
    const arr = [...filteredResults];
    if (sortOrder === 'date') {
      arr.sort((a, b) => b.source_version_id - a.source_version_id);
    } else if (sortOrder === 'source') {
      arr.sort((a, b) => a.source_id.localeCompare(b.source_id));
    }
    // 'relevance' keeps original API order
    return arr;
  }, [filteredResults, sortOrder]);

  // Facets derived from all (unfiltered) results
  const facetGroups = useMemo(() => {
    const domainCounts = new Map<string, number>();
    const adapterCounts = new Map<string, number>();
    allResults.forEach((r) => {
      domainCounts.set(r.domain, (domainCounts.get(r.domain) ?? 0) + 1);
      adapterCounts.set(r.adapter_id, (adapterCounts.get(r.adapter_id) ?? 0) + 1);
    });
    const scoreBuckets = [
      { value: 'high', label: 'High (≥0.80)', count: allResults.filter((r) => r.similarity_score >= 0.8).length },
      { value: 'medium', label: 'Medium (≥0.60)', count: allResults.filter((r) => r.similarity_score >= 0.6 && r.similarity_score < 0.8).length },
      { value: 'low', label: 'Low (<0.60)', count: allResults.filter((r) => r.similarity_score < 0.6).length },
    ].filter((b) => b.count > 0);

    return [
      {
        title: 'Domain',
        items: Array.from(domainCounts.entries()).map(([domain, count]) => ({
          value: domain,
          label: capitalize(domain),
          count,
          color: getDomainColor(domain),
        })),
      },
      {
        title: 'Similarity',
        items: scoreBuckets,
      },
      {
        title: 'Adapter',
        items: Array.from(adapterCounts.entries()).map(([adapter, count]) => ({
          value: adapter,
          label: adapter,
          count,
        })),
      },
    ].filter((g) => g.items.length > 0);
  }, [allResults]);

  const hasQuery = !!(search.q?.trim());
  const resultMeta = hasQuery && !isLoading && !error
    ? `${sortedResults.length} result${sortedResults.length !== 1 ? 's' : ''}`
    : undefined;

  const handleSuggestedQuery = (q: string) => {
    setInputValue(q);
    navigate({ to: '/search', search: { q, domain: domainFilter[0] } });
  };

  const handleViewInBrowser = useCallback(
    (result: QueryResultItem) => {
      navigate({
        to: '/browser',
        search: {
          domain: result.domain,
          table: 'chunks',
          source_id: result.source_id,
          q: result.chunk_hash,
        },
      });
    },
    [navigate]
  );

  const filterBar = (
    <>
      <FilterDropdown
        mode="radio"
        value={domainFilter}
        onChange={handleDomainFilterChange}
      >
        <FilterDropdown.Trigger
          label="Domain"
          summary={domainFilter.length > 0 ? capitalize(domainFilter[0]) : 'All'}
        />
        <FilterDropdown.Panel>
          <FilterDropdown.Section>
            <FilterDropdown.Radio value="" label="All Domains" />
            {SEARCH_DOMAINS.map((d) => (
              <FilterDropdown.Radio key={d} value={d} label={capitalize(d)} />
            ))}
          </FilterDropdown.Section>
        </FilterDropdown.Panel>
      </FilterDropdown>

      <FilterDropdown
        mode="checkbox"
        value={adapterFilter}
        onChange={setAdapterFilter}
      >
        <FilterDropdown.Trigger
          label="Adapter"
          summary={adapterFilter.length > 0 ? `${adapterFilter.length} selected` : 'All'}
        />
        <FilterDropdown.Panel>
          <FilterDropdown.Section>
            {availableAdapters.map((id) => (
              <FilterDropdown.Checkbox key={id} value={id} label={id} />
            ))}
          </FilterDropdown.Section>
        </FilterDropdown.Panel>
      </FilterDropdown>

      <FilterDropdown
        mode="radio"
        value={[minScore]}
        onChange={(vals) => setMinScore(vals[0] ?? 'any')}
      >
        <FilterDropdown.Trigger
          label="Score"
          summary={minScore === 'any' ? 'Any' : minScore.charAt(0).toUpperCase() + minScore.slice(1)}
        />
        <FilterDropdown.Panel>
          <FilterDropdown.Section title="Minimum similarity">
            <FilterDropdown.Radio value="any" label="Any" />
            <FilterDropdown.Radio value="high" label="High (≥0.80)" />
            <FilterDropdown.Radio value="medium" label="Medium (≥0.60)" />
            <FilterDropdown.Radio value="low" label="Low (≥0.40)" />
          </FilterDropdown.Section>
        </FilterDropdown.Panel>
      </FilterDropdown>
    </>
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        eyebrow="Library"
        title="Search"
        subtitle="Semantic search across your knowledge base"
      />
      <div className="flex flex-col flex-1 min-h-0 p-6 gap-4 overflow-auto">

        {/* Search hero with filters */}
        <SearchHero
          query={inputValue}
          onQueryChange={(val) => {
            setInputValue(val);
            setSelectedResult(null);
          }}
          onSearch={() => {
            const trimmed = inputValue.trim();
            if (!trimmed) return;
            navigate({ to: '/search', search: { ...searchRef.current, q: trimmed } });
          }}
          resultMeta={resultMeta}
          filters={filterBar}
          className="shrink-0"
        />

        {/* Error banner */}
        {error && (
          <div
            className="rounded-xl px-4 py-3 text-sm shrink-0"
            style={{
              background: 'rgb(var(--status-error) / 0.08)',
              border: '1px solid rgb(var(--status-error) / 0.25)',
              color: 'rgb(var(--status-error))',
            }}
          >
            <strong>Search error: </strong>
            {error instanceof Error ? error.message : 'Unknown error'}
          </div>
        )}

        {/* Main area */}
        <div className="flex gap-4 flex-1 min-h-0">

          {/* Results column */}
          <div className="flex flex-col gap-3 flex-1 min-h-0 overflow-y-auto">
            {isLoading && !error && (
              <div className="flex flex-col gap-2">
                {[...Array(5)].map((_, i) => <SkeletonCard key={i} />)}
              </div>
            )}

            {!isLoading && hasQuery && !error && (
              <>
                {/* Sort controls */}
                <div className="flex items-center justify-between shrink-0">
                  <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                    {sortedResults.length} result{sortedResults.length !== 1 ? 's' : ''} for &ldquo;{search.q}&rdquo;
                  </span>
                  <SegmentedControl
                    value={sortOrder}
                    onChange={setSortOrder}
                    options={SORT_OPTIONS}
                  />
                </div>

                {/* Result cards */}
                {sortedResults.length > 0 ? (
                  sortedResults.map((result) => (
                    <ResultCard
                      key={result.chunk_hash}
                      domain={capitalize(result.domain)}
                      source={result.adapter_id}
                      version={String(result.source_version_id)}
                      snippet={highlightSnippet(result, search.q ?? '')}
                      provenance={{
                        document: result.source_id,
                        section: `${result.chunk_type} · ${shortHash(result.chunk_hash)}`,
                      }}
                      score={result.similarity_score}
                      selected={selectedResult?.chunk_hash === result.chunk_hash}
                      onOpen={() =>
                        setSelectedResult(
                          selectedResult?.chunk_hash === result.chunk_hash ? null : result
                        )
                      }
                      actions={[
                        {
                          label: 'View in Browser',
                          icon: 'send',
                          onClick: () => handleViewInBrowser(result),
                        },
                      ]}
                    />
                  ))
                ) : (
                  <div
                    className="rounded-xl p-8 flex flex-col items-center gap-2"
                    style={{ background: 'rgb(var(--canvas-surface))', border: '1px solid rgb(var(--canvas-border))' }}
                  >
                    <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                      No results found
                    </p>
                    <p className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                      Try adjusting your query or removing filters
                    </p>
                  </div>
                )}
              </>
            )}

            {!hasQuery && !isLoading && (
              <EmptyState onSelect={handleSuggestedQuery} />
            )}
          </div>

          {/* Facets sidebar */}
          {hasQuery && facetGroups.length > 0 && (
            <div
              className="w-52 shrink-0 rounded-xl overflow-hidden"
              style={{
                background: 'rgb(var(--canvas-surface))',
                border: '1px solid rgb(var(--canvas-border))',
                alignSelf: 'flex-start',
              }}
            >
              <div
                className="px-3 py-2 text-xs font-semibold"
                style={{
                  color: 'rgb(var(--canvas-fg-2))',
                  borderBottom: '1px solid rgb(var(--canvas-border))',
                }}
              >
                Refine
              </div>
              <FacetList
                groups={facetGroups}
                onItemClick={(group, item) => {
                  if (group.title === 'Domain') {
                    handleDomainFilterChange([item.value]);
                  } else if (group.title === 'Adapter') {
                    setAdapterFilter((prev) =>
                      prev.includes(item.value)
                        ? prev.filter((v) => v !== item.value)
                        : [...prev, item.value]
                    );
                  } else if (group.title === 'Similarity') {
                    setMinScore(item.value);
                  }
                }}
              />
            </div>
          )}
        </div>

        {/* Detail drawer */}
        <DetailDrawer
          result={selectedResult}
          isOpen={!!selectedResult}
          onClose={() => setSelectedResult(null)}
          onViewInBrowser={() => selectedResult && handleViewInBrowser(selectedResult)}
        />
      </div>
    </div>
  );
}
