import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useRouterState } from '@tanstack/react-router';
import {
  MagnifyingGlassIcon,
  XMarkIcon,
  ArrowRightIcon,
  ArrowTopRightOnSquareIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import { useSearch } from '../hooks/useSearch';
import type { SearchPageSearch } from '../router';
import type { QueryResultItem } from '../types/api';
import { getDomainColor, domainColors, colors } from '../lib/designTokens';

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

function DomainChip({
  domain,
  active,
  onClick,
}: {
  domain: string;
  active: boolean;
  onClick: () => void;
}) {
  const color = domain === 'all' ? colors.accent : getDomainColor(domain);
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-3 h-7 rounded-full text-xs font-medium transition-all shrink-0"
      style={
        active
          ? { background: `${color}26`, color, border: `1px solid ${color}` }
          : {
              background: 'transparent',
              color: colors.textMuted,
              border: `1px solid ${colors.border}`,
            }
      }
    >
      {domain === 'all' ? 'All Domains' : capitalize(domain)}
    </button>
  );
}

// ── Score bar ─────────────────────────────────────────────────────

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.8 ? colors.statusGreen : score >= 0.6 ? colors.statusAmber : colors.textDim;
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <div
        className="rounded-full overflow-hidden"
        style={{ width: 36, height: 4, background: colors.bgElevated }}
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
        background: selected ? `${domainColor}12` : colors.bgSurface,
        border: `1px solid ${selected ? domainColor : focused ? colors.textDim : colors.border}`,
        outline: 'none',
      }}
    >
      {/* Top row: domain badge + adapter + score */}
      <div className="flex items-center gap-2">
        <span
          className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
          style={{ background: `${domainColor}20`, color: domainColor }}
        >
          {capitalize(result.domain)}
        </span>
        <span className="text-xs truncate flex-1" style={{ color: colors.textDim }}>
          {result.adapter_id}
        </span>
        <ScoreBar score={result.similarity_score} />
      </div>

      {/* Snippet */}
      <p
        className="text-xs leading-relaxed line-clamp-3"
        style={{ color: colors.textMuted }}
      >
        {highlightedParts.map((part, i) =>
          i % 2 === 1 ? (
            <mark
              key={i}
              className="rounded px-0.5"
              style={{
                background: `${domainColor}30`,
                color: colors.textPrimary,
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
        <span className="text-[11px]" style={{ color: colors.textDim }}>
          {shortId(result.source_id)}
        </span>
        <span className="text-[11px]" style={{ color: colors.textDim }}>·</span>
        <span className="text-[11px]" style={{ color: colors.textDim }}>
          {result.chunk_type}
        </span>
        <ChevronRightIcon
          className="w-3 h-3 ml-auto shrink-0"
          style={{ color: selected ? domainColor : colors.textDim }}
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
      style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
    >
      <div className="flex items-center gap-2">
        <div className="w-16 h-5 rounded-full animate-pulse" style={{ background: colors.bgElevated }} />
        <div className="flex-1 h-3 rounded animate-pulse" style={{ background: colors.bgElevated }} />
        <div className="w-16 h-3 rounded animate-pulse" style={{ background: colors.bgElevated }} />
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="h-3 rounded animate-pulse w-full" style={{ background: colors.bgElevated }} />
        <div className="h-3 rounded animate-pulse w-4/5" style={{ background: colors.bgElevated }} />
        <div className="h-3 rounded animate-pulse w-3/5" style={{ background: colors.bgElevated }} />
      </div>
      <div className="flex gap-2">
        <div className="h-3 rounded animate-pulse w-32" style={{ background: colors.bgElevated }} />
      </div>
    </div>
  );
}

// ── Detail panel ──────────────────────────────────────────────────

function DetailPanel({
  result,
  onClose,
  onViewInBrowser,
}: {
  result: QueryResultItem;
  onClose: () => void;
  onViewInBrowser: () => void;
}) {
  const domainColor = getDomainColor(result.domain);
  const fullContent = result.context_header
    ? `${result.context_header}\n\n${result.chunk_text}`
    : result.chunk_text;

  return (
    <div
      className="rounded-xl flex flex-col min-h-0 overflow-hidden"
      style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0 border-b"
        style={{ borderColor: colors.border }}
      >
        <span className="text-sm font-semibold" style={{ color: colors.textPrimary }}>
          Result Detail
        </span>
        <button
          onClick={onClose}
          className="w-6 h-6 flex items-center justify-center rounded"
          style={{ color: colors.textDim }}
          aria-label="Close detail panel"
        >
          <XMarkIcon className="w-4 h-4" />
        </button>
      </div>

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
              <span className="text-xs shrink-0" style={{ color: colors.textDim }}>
                {label}
              </span>
              <span
                className="text-xs font-medium text-right"
                style={{ color: color ?? colors.textPrimary }}
              >
                {value}
              </span>
            </div>
          ))}

          {/* Hash (full row, monospace) */}
          <div className="flex flex-col gap-1">
            <span className="text-xs" style={{ color: colors.textDim }}>Chunk hash</span>
            <span
              className="text-[11px] font-mono break-all"
              style={{ color: colors.textMuted }}
            >
              {result.chunk_hash}
            </span>
          </div>

          {/* Source ID */}
          <div className="flex flex-col gap-1">
            <span className="text-xs" style={{ color: colors.textDim }}>Source ID</span>
            <span
              className="text-[11px] font-mono break-all"
              style={{ color: colors.textMuted }}
            >
              {result.source_id}
            </span>
          </div>
        </div>

        {/* Divider */}
        <div className="h-px" style={{ background: colors.border }} />

        {/* Full content */}
        <div className="flex flex-col gap-2">
          <span className="text-xs font-semibold" style={{ color: colors.textPrimary }}>
            Full Content
          </span>
          <p
            className="text-xs leading-relaxed whitespace-pre-wrap"
            style={{ color: colors.textMuted }}
          >
            {fullContent}
          </p>
        </div>
      </div>

      {/* Footer action */}
      <div
        className="px-4 py-3 shrink-0 border-t"
        style={{ borderColor: colors.border }}
      >
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
  );
}

// ── Empty state ───────────────────────────────────────────────────

function EmptyState({ onSelect }: { onSelect: (q: string) => void }) {
  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 56, height: 56, background: `${colors.accent}1A` }}
      >
        <MagnifyingGlassIcon className="w-7 h-7" style={{ color: colors.accent }} />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: colors.textPrimary }}>
          Search your knowledge base
        </p>
        <p className="text-xs" style={{ color: colors.textDim }}>
          Semantic search across all ingested content
        </p>
      </div>
      <div className="flex flex-col gap-2 w-full max-w-md">
        <p className="text-xs mb-1 text-center" style={{ color: colors.textDim }}>
          Try asking…
        </p>
        {SUGGESTED_QUERIES.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            className="flex items-center gap-2.5 px-4 py-2.5 rounded-lg text-left transition-colors group"
            style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = colors.accent;
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = colors.border;
            }}
          >
            <ArrowRightIcon className="w-3.5 h-3.5 shrink-0" style={{ color: colors.textDim }} />
            <span className="text-xs" style={{ color: colors.textMuted }}>
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
  const search = (routerState.location.search ?? {}) as SearchPageSearch;

  const inputRef = useRef<HTMLInputElement>(null);
  const cardRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  // Always holds the latest search params — used by debounce effect to avoid stale closures
  const searchRef = useRef(search);

  // Local input value — debounced to URL
  const [inputValue, setInputValue] = useState(search.q ?? '');
  // Selected domain chip — also drives URL
  const [selectedDomain, setSelectedDomain] = useState(search.domain ?? '');
  // Selected result for detail panel
  const [selectedResult, setSelectedResult] = useState<QueryResultItem | null>(null);
  // Keyboard-focused index
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);

  // Keep searchRef current so debounce effect always reads the latest URL params
  searchRef.current = search;

  // Sync input if URL changes externally (browser back/forward)
  useEffect(() => {
    setInputValue(search.q ?? '');
    setSelectedDomain(search.domain ?? '');
  }, [search.q, search.domain]);

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
          background: colors.bgSurface,
          border: `1px solid ${colors.border}`,
        }}
        onClick={() => inputRef.current?.focus()}
      >
        <MagnifyingGlassIcon className="w-5 h-5 shrink-0" style={{ color: colors.textDim }} />
        <input
          ref={inputRef}
          type="text"
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-[#6B7280]"
          style={{ color: colors.textPrimary }}
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
            style={{ borderColor: `${colors.accent} transparent transparent transparent` }}
          />
        )}
        {inputValue && !isLoading && (
          <button onClick={handleClear} aria-label="Clear search">
            <XMarkIcon className="w-4 h-4" style={{ color: colors.textDim }} />
          </button>
        )}
        <kbd
          className="text-[10px] rounded px-1.5 py-0.5 shrink-0"
          style={{ background: colors.bgElevated, color: colors.textDim }}
        >
          ⏎
        </kbd>
      </div>

      {/* Domain filter chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-0.5 shrink-0">
        <span className="text-xs shrink-0 mr-1" style={{ color: colors.textDim }}>
          Filter:
        </span>
        <DomainChip
          domain="all"
          active={!selectedDomain}
          onClick={() => handleDomainSelect('')}
        />
        {SEARCH_DOMAINS.map((d) => (
          <DomainChip
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
          className="flex flex-col gap-2 overflow-y-auto min-h-0"
          style={{ width: selectedResult ? '58%' : '100%', transition: 'width 200ms ease' }}
        >
          {/* Error */}
          {error && (
            <div
              className="rounded-xl px-4 py-3 text-sm"
              style={{
                background: `${colors.statusRed}14`,
                border: `1px solid ${colors.statusRed}40`,
                color: colors.statusRed,
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
                <p className="text-xs shrink-0 mb-1" style={{ color: colors.textDim }}>
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
                  style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
                >
                  <p className="text-sm" style={{ color: colors.textMuted }}>
                    No results found
                  </p>
                  <p className="text-xs" style={{ color: colors.textDim }}>
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

        {/* Detail panel */}
        {selectedResult && (
          <div className="flex-1 min-h-0 overflow-y-auto">
            <DetailPanel
              result={selectedResult}
              onClose={() => setSelectedResult(null)}
              onViewInBrowser={() => handleViewInBrowser(selectedResult)}
            />
          </div>
        )}
      </div>
    </div>
  );
}
