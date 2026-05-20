import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useRouterState } from '@tanstack/react-router';
import {
  MagnifyingGlassIcon,
  XMarkIcon,
  ArrowRightIcon,
  ArrowTopRightOnSquareIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import { Chip, Drawer } from '@tinkermonkey/heimdall-ui';
import { useSearch } from '../hooks/useSearch';
import { useToast } from '../hooks/useToast';
import type { SearchPageSearch } from '../router';
import type { QueryResultItem } from '../types/api';
import { getDomainColor, getDomainColorWithAlpha, domainColors } from '../lib/designTokens';

// ── Helpers ───────────────────────────────────────────────────────

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function shortId(id: string): string {
  return id.length > 28 ? `${id.substring(0, 28)}…` : id;
}

// ── Constants ─────────────────────────────────────────────────────

// All searchable domains — full set from design tokens (superset of registry)
const SEARCH_DOMAINS = Object.keys(domainColors);

const SUGGESTED_QUERIES = [
  'What did I read about machine learning last month?',
  'Recent messages from my team',
  'Health trends this week',
  'Open tasks due soon',
  'Notes about architecture decisions',
  'Documents related to my projects',
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

// ── Domain chip ───────────────────────────────────────────────────

function DomainChipButton({
  domain,
  active,
  onClick,
}: {
  domain: string;
  active: boolean;
  onClick: () => void;
}) {
  const label = domain === 'all' ? 'All Domains' : capitalize(domain);
  const color = domain === 'all' ? 'rgb(var(--accent-primary))' : getDomainColor(domain);
  const bgColor = domain === 'all'
    ? 'rgb(var(--accent-primary) / 0.15)'
    : getDomainColorWithAlpha(domain, '26');

  const baseStyle = { display: 'inline-block' as const, padding: '2px 12px', height: '28px', lineHeight: '24px' };

  return (
    <button
      onClick={onClick}
      className="shrink-0 transition-all p-0 border-0 bg-transparent"
    >
      <Chip
        className="text-xs font-medium"
        style={
          active
            ? { ...baseStyle, background: bgColor, color, border: `1px solid ${color}` }
            : { ...baseStyle, background: 'transparent', color: 'rgb(var(--canvas-fg-2))', border: `1px solid rgb(var(--canvas-border))` }
        }
      >
        {label}
      </Chip>
    </button>
  );
}

// ── Score bar ─────────────────────────────────────────────────────

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.8 ? 'rgb(var(--status-ok))' : score >= 0.6 ? 'rgb(var(--status-amber))' : 'rgb(var(--canvas-fg-3))';
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <div
        className="rounded-full overflow-hidden"
        style={{ width: 36, height: 4, background: 'rgb(var(--canvas-surface))' }}
      >
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-[11px] tabular-nums font-medium" style={{ color }}>
        {score.toFixed(2)}
      </span>
    </div>
  );
}

// ── Result card ───────────────────────────────────────────────────

function ResultCard({
  result,
  selected,
  focused,
  query,
  onClick,
  registerRef,
}: {
  result: QueryResultItem;
  selected: boolean;
  focused: boolean;
  query: string;
  onClick: () => void;
  registerRef?: (el: HTMLButtonElement | null) => void;
}) {
  const domainColor = getDomainColor(result.domain);

  // Keyword highlight: split with a capture-group regex so odd indices are matches.
  // e.g. "foo bar baz".split(/(bar)/i) → ["foo ", "bar", " baz"]
  const highlightedParts = useMemo(() => {
    const snippet = result.context_header
      ? `${result.context_header}\n\n${result.chunk_text}`
      : result.chunk_text;
    const preview = snippet.substring(0, 280);
    const terms = query
      .split(/\s+/)
      .filter((t) => t.length > 2)
      .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    if (terms.length === 0) return [preview];
    const pattern = new RegExp(`(${terms.join('|')})`, 'gi');
    return preview.split(pattern);
  }, [result, query]);

  return (
    <button
      ref={registerRef}
      onClick={onClick}
      className="w-full text-left rounded-xl p-4 transition-colors flex flex-col gap-2"
      style={{
        background: selected ? getDomainColorWithAlpha(result.domain, '12') : 'rgb(var(--canvas-surface))',
        border: `1px solid ${selected ? domainColor : focused ? 'rgb(var(--canvas-fg-3))' : 'rgb(var(--canvas-border))'}`,
        outline: 'none',
      }}
    >
      {/* Top row: domain badge + adapter + score */}
      <div className="flex items-center gap-2">
        <span
          className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
          style={{ background: getDomainColorWithAlpha(result.domain, '20'), color: domainColor }}
        >
          {capitalize(result.domain)}
        </span>
        <span className="text-xs truncate flex-1" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          {result.adapter_id}
        </span>
        <ScoreBar score={result.similarity_score} />
      </div>

      {/* Snippet */}
      <p
        className="text-xs leading-relaxed line-clamp-3"
        style={{ color: 'rgb(var(--canvas-fg-2))' }}
      >
        {highlightedParts.map((part, i) =>
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
        {result.chunk_text.length > 280 ? '…' : ''}
      </p>

      {/* Bottom row: source + chunk type */}
      <div className="flex items-center gap-2">
        <span className="text-[11px]" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          {shortId(result.source_id)}
        </span>
        <span className="text-[11px]" style={{ color: 'rgb(var(--canvas-fg-3))' }}>·</span>
        <span className="text-[11px]" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          {result.chunk_type}
        </span>
        <ChevronRightIcon
          className="w-3 h-3 ml-auto shrink-0"
          style={{ color: selected ? domainColor : 'rgb(var(--canvas-fg-3))' }}
        />
      </div>
    </button>
  );
}

// ── Skeleton card ─────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-3"
      style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-border))` }}
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
      <div className="flex gap-2">
        <div className="h-3 rounded animate-pulse w-32" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
      </div>
    </div>
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
  if (!result) return null;

  const domainColor = getDomainColor(result.domain);
  const fullContent = result.context_header
    ? `${result.context_header}\n\n${result.chunk_text}`
    : result.chunk_text;

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      position="right"
      title="Result Detail"
      className="flex flex-col"
    >
      <div className="flex flex-col gap-5 p-4 overflow-y-auto flex-1">
        {/* Metadata grid */}
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
              <span
                className="text-xs font-medium text-right"
                style={{ color: color ?? 'rgb(var(--canvas-fg-1))' }}
              >
                {value}
              </span>
            </div>
          ))}

          {/* Hash (full row, monospace) */}
          <div className="flex flex-col gap-1">
            <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Chunk hash</span>
            <span
              className="text-[11px] font-mono break-all"
              style={{ color: 'rgb(var(--canvas-fg-2))' }}
            >
              {result.chunk_hash}
            </span>
          </div>

          {/* Source ID */}
          <div className="flex flex-col gap-1">
            <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Source ID</span>
            <span
              className="text-[11px] font-mono break-all"
              style={{ color: 'rgb(var(--canvas-fg-2))' }}
            >
              {result.source_id}
            </span>
          </div>
        </div>

        {/* Divider */}
        <div className="h-px" style={{ background: 'rgb(var(--canvas-border))' }} />

        {/* Full content */}
        <div className="flex flex-col gap-2">
          <span className="text-xs font-semibold" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
            Full Content
          </span>
          <p
            className="text-xs leading-relaxed whitespace-pre-wrap"
            style={{ color: 'rgb(var(--canvas-fg-2))' }}
          >
            {fullContent}
          </p>
        </div>

        {/* Footer action */}
        <div className="pt-4 border-t" style={{ borderColor: 'rgb(var(--canvas-border))' }}>
          <button
            onClick={onViewInBrowser}
            className="flex items-center gap-1.5 text-xs font-medium transition-colors"
            style={{ color: domainColor }}
          >
            <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" />
            View in Browser
          </button>
        </div>
      </div>
    </Drawer>
  );
}

// ── Empty state ───────────────────────────────────────────────────

function EmptyState({ onSelect }: { onSelect: (q: string) => void }) {
  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 56, height: 56, background: `rgb(var(--accent-primary) / 0.1)` }}
      >
        <MagnifyingGlassIcon className="w-7 h-7" style={{ color: 'rgb(var(--accent-primary))' }} />
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
            className="flex items-center gap-2.5 px-4 py-2.5 rounded-lg text-left transition-colors group"
            style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-border))` }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = 'rgb(var(--accent-primary))';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = 'rgb(var(--canvas-border))';
            }}
          >
            <ArrowRightIcon className="w-3.5 h-3.5 shrink-0" style={{ color: 'rgb(var(--canvas-fg-3))' }} />
            <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
              {q}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Search page ───────────────────────────────────────────────────

export default function SearchPage() {
  const navigate = useNavigate();
  const routerState = useRouterState();
  const { showToast } = useToast();
  const search = (routerState.location.search ?? {}) as SearchPageSearch;

  const inputRef = useRef<HTMLInputElement>(null);
  const cardRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  // Always holds the latest search params — used by debounce effect to avoid stale closures
  const searchRef = useRef(search);
  // Track previous search params to detect external URL changes (back/forward)
  const prevSearchRef = useRef(search);

  // Local input value — debounced to URL
  const [inputValue, setInputValue] = useState(search.q ?? '');
  // Selected domain chip — also drives URL
  const [selectedDomain, setSelectedDomain] = useState(search.domain ?? '');
  // Selected result for detail panel
  const [selectedResult, setSelectedResult] = useState<QueryResultItem | null>(null);
  // Keyboard-focused index
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);

  // Sync input if URL changes externally (browser back/forward)
  useEffect(() => {
    if (search.q !== prevSearchRef.current.q) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setInputValue(search.q ?? '');
    }
    if (search.domain !== prevSearchRef.current.domain) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedDomain(search.domain ?? '');
    }
    prevSearchRef.current = search;
  }, [search]);

  // Keep searchRef current so debounce effect always reads the latest URL params
  useEffect(() => {
    searchRef.current = search;
  }, [search]);

  // Debounce the input value (300ms) then push to URL.
  // Uses searchRef (not search directly) so the effect never captures stale params —
  // a domain chip click that fires between a keystroke and the debounce won't be overwritten.
  const debouncedQuery = useDebounce(inputValue, 300);
  useEffect(() => {
    if (debouncedQuery === (searchRef.current.q ?? '')) return;
    navigate({
      to: '/search',
      search: {
        ...searchRef.current,
        q: debouncedQuery || undefined,
      },
    });
  }, [debouncedQuery, navigate]);

  // Update URL when domain chip changes
  const handleDomainSelect = useCallback(
    (domain: string) => {
      setSelectedDomain(domain);
      setSelectedResult(null);
      setFocusedIndex(-1);
      navigate({
        to: '/search',
        search: {
          ...search,
          q: inputValue || undefined,
          domain: domain || undefined,
        },
      });
    },
    [navigate, search, inputValue]
  );

  // Focus input on '/' keypress (global shortcut)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.key === '/' &&
        document.activeElement !== inputRef.current &&
        !(e.target instanceof HTMLInputElement) &&
        !(e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const { data, isLoading, error } = useSearch(search);
  const results = data?.results ?? [];

  // Show error toast when search fails
  useEffect(() => {
    if (error) {
      showToast({
        title: 'Search Error',
        subtitle: error instanceof Error ? error.message : 'Failed to search',
        variant: 'error',
      });
    }
  }, [error, showToast]);

  // Keyboard navigation on the results list
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (results.length === 0) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const next = Math.min(focusedIndex + 1, results.length - 1);
        setFocusedIndex(next);
        cardRefs.current.get(next)?.focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prev = Math.max(focusedIndex - 1, 0);
        setFocusedIndex(prev);
        cardRefs.current.get(prev)?.focus();
      } else if (e.key === 'Escape') {
        setSelectedResult(null);
        setFocusedIndex(-1);
        inputRef.current?.focus();
      } else if (e.key === 'Enter' && focusedIndex >= 0) {
        setSelectedResult(results[focusedIndex]);
      }
    },
    [results, focusedIndex]
  );

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      // Bypass the 300ms debounce — fire immediately on Enter
      const trimmed = inputValue.trim();
      if (!trimmed) return;
      navigate({
        to: '/search',
        search: { ...searchRef.current, q: trimmed },
      });
    } else if (e.key === 'Escape') {
      setSelectedResult(null);
      (e.currentTarget as HTMLInputElement).blur();
    } else if (e.key === 'ArrowDown' && results.length > 0) {
      e.preventDefault();
      setFocusedIndex(0);
      cardRefs.current.get(0)?.focus();
    }
  };

  const handleClear = () => {
    setInputValue('');
    setSelectedDomain('');
    setSelectedResult(null);
    setFocusedIndex(-1);
    navigate({ to: '/search', search: {} });
    inputRef.current?.focus();
  };

  const handleSuggestedQuery = (q: string) => {
    setInputValue(q);
    navigate({
      to: '/search',
      search: { q, domain: selectedDomain || undefined },
    });
    inputRef.current?.focus();
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

  const hasQuery = !!(search.q?.trim());

  return (
    <div
      className="flex flex-col h-full min-h-0 p-6 gap-4"
      onKeyDown={handleKeyDown}
    >
      {/* Search input */}
      <div
        className="flex items-center gap-3 rounded-xl px-4 h-12 shrink-0"
        style={{
          background: 'rgb(var(--canvas-surface))',
          border: `1px solid rgb(var(--canvas-border))`,
        }}
        onClick={() => inputRef.current?.focus()}
      >
        <MagnifyingGlassIcon className="w-5 h-5 shrink-0" style={{ color: 'rgb(var(--canvas-fg-3))' }} />
        <input
          ref={inputRef}
          type="text"
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-[#6B7280]"
          style={{ color: 'rgb(var(--canvas-fg-1))' }}
          placeholder="Search your knowledge base…"
          value={inputValue}
          onChange={(e) => {
            setInputValue(e.target.value);
            setSelectedResult(null);
            setFocusedIndex(-1);
          }}
          onKeyDown={handleInputKeyDown}
          autoFocus
          autoComplete="off"
          spellCheck={false}
        />
        {isLoading && (
          <div
            className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin shrink-0"
            style={{ borderColor: `rgb(var(--accent-primary)) transparent transparent transparent` }}
          />
        )}
        {inputValue && !isLoading && (
          <button onClick={handleClear} aria-label="Clear search">
            <XMarkIcon className="w-4 h-4" style={{ color: 'rgb(var(--canvas-fg-3))' }} />
          </button>
        )}
        <kbd
          className="text-[10px] rounded px-1.5 py-0.5 shrink-0"
          style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-3))' }}
        >
          ⏎
        </kbd>
      </div>

      {/* Domain filter chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-0.5 shrink-0">
        <span className="text-xs shrink-0 mr-1" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          Filter:
        </span>
        <DomainChipButton
          domain="all"
          active={!selectedDomain}
          onClick={() => handleDomainSelect('')}
        />
        {SEARCH_DOMAINS.map((d) => (
          <DomainChipButton
            key={d}
            domain={d}
            active={selectedDomain === d}
            onClick={() => handleDomainSelect(selectedDomain === d ? '' : d)}
          />
        ))}
      </div>

      {/* Main area */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Results list */}
        <div
          className="flex flex-col gap-2 overflow-y-auto min-h-0 flex-1"
        >
          {/* Error */}
          {error && (
            <div
              className="rounded-xl px-4 py-3 text-sm"
              style={{
                background: `rgb(var(--status-error) / 0.08)`,
                border: `1px solid rgb(var(--status-error) / 0.25)`,
                color: 'rgb(var(--status-error))',
              }}
            >
              <strong>Search error: </strong>
              {error instanceof Error ? error.message : 'Unknown error'}
            </div>
          )}

          {/* Loading skeletons */}
          {isLoading && !error && (
            <div className="flex flex-col gap-2">
              {[...Array(5)].map((_, i) => <SkeletonCard key={i} />)}
            </div>
          )}

          {/* Results */}
          {!isLoading && hasQuery && !error && (
            <>
              {results.length > 0 && (
                <p className="text-xs shrink-0 mb-1" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  {data!.total} result{data!.total !== 1 ? 's' : ''} for &ldquo;{search.q}&rdquo;
                </p>
              )}
              {results.length > 0 ? (
                results.map((result, i) => (
                  <ResultCard
                    key={result.chunk_hash}
                    result={result}
                    selected={selectedResult?.chunk_hash === result.chunk_hash}
                    focused={focusedIndex === i}
                    query={search.q ?? ''}
                    onClick={() => {
                      setSelectedResult(
                        selectedResult?.chunk_hash === result.chunk_hash ? null : result
                      );
                      setFocusedIndex(i);
                    }}
                    registerRef={(el) => {
                      if (el) cardRefs.current.set(i, el);
                      else cardRefs.current.delete(i);
                    }}
                  />
                ))
              ) : (
                <div
                  className="rounded-xl p-8 flex flex-col items-center gap-2"
                  style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-border))` }}
                >
                  <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                    No results found
                  </p>
                  <p className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                    Try adjusting your query or removing domain filters
                  </p>
                </div>
              )}
            </>
          )}

          {/* Empty state */}
          {!hasQuery && !isLoading && (
            <EmptyState onSelect={handleSuggestedQuery} />
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

