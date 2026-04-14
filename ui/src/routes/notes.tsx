import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  ChevronDownIcon,
  MagnifyingGlassIcon,
  TagIcon,
} from '@heroicons/react/24/outline';
import { useSources } from '../hooks/useSources';
import { fetchSourceChunks } from '../api/client';
import { colors, getDomainColor } from '../lib/designTokens';
import type { SourceSummary, ChunkResponse } from '../types/api';

const noteColor = getDomainColor('notes'); // #6366F1

// ── Helpers ──────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 2) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function adapterLabel(adapterId: string): string {
  const base = adapterId.split(':')[0];
  return base.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function noteTitle(source: SourceSummary): string {
  if (source.display_name) return source.display_name;
  const parts = source.origin_ref.split('/');
  const filename = parts[parts.length - 1];
  return filename.replace(/\.(md|txt|note)$/i, '') || source.origin_ref;
}

function adapterPrefix(adapterId: string): string {
  return adapterId.split(':')[0];
}

// ── Inline text renderer ──────────────────────────────────────────

/**
 * Tokenises a single line of markdown for inline formatting.
 * Handles: **bold**, `code`, [[wikilink]].
 * Keeps implementation simple — a single-pass regex split.
 */
function InlineText({ text }: { text: string }): ReactNode {
  const tokenRegex = /(\*\*[^*]+\*\*|`[^`]+`|\[\[[^\]]+\]\])/g;
  const parts: { type: 'text' | 'bold' | 'code' | 'wikilink'; content: string }[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: text.slice(lastIndex, match.index) });
    }
    const token = match[0];
    if (token.startsWith('**')) {
      parts.push({ type: 'bold', content: token.slice(2, -2) });
    } else if (token.startsWith('`')) {
      parts.push({ type: 'code', content: token.slice(1, -1) });
    } else {
      parts.push({ type: 'wikilink', content: token.slice(2, -2) });
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    parts.push({ type: 'text', content: text.slice(lastIndex) });
  }

  return (
    <>
      {parts.map((part, i) => {
        if (part.type === 'bold') {
          return (
            <strong key={i} className="font-semibold" style={{ color: colors.textPrimary }}>
              {part.content}
            </strong>
          );
        }
        if (part.type === 'code') {
          return (
            <code
              key={i}
              className="px-1 rounded text-xs font-mono"
              style={{ background: colors.bgElevated, color: '#93C5FD' }}
            >
              {part.content}
            </code>
          );
        }
        if (part.type === 'wikilink') {
          return (
            <span
              key={i}
              className="rounded px-0.5 text-xs"
              style={{ color: noteColor, background: `${noteColor}20` }}
            >
              {part.content}
            </span>
          );
        }
        return <span key={i}>{part.content}</span>;
      })}
    </>
  );
}

// ── Dark markdown block renderer ──────────────────────────────────

/**
 * Renders markdown content with dark-theme styling.
 * Handles: fenced code blocks, headings (h1–h3), unordered/ordered lists,
 * blockquotes, horizontal rules, and paragraphs.
 */
function DarkMarkdownContent({ content }: { content: string }): ReactNode {
  const lines = content.split('\n');
  const nodes: ReactNode[] = [];
  let i = 0;
  let k = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (line.trimStart().startsWith('```')) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      nodes.push(
        <pre
          key={k++}
          className="overflow-x-auto rounded p-3 text-xs font-mono leading-relaxed my-3"
          style={{ background: colors.bgElevated, color: '#93C5FD', border: `1px solid ${colors.border}` }}
        >
          <code>{codeLines.join('\n')}</code>
        </pre>,
      );
      i++; // skip closing ```
      continue;
    }

    // Headings
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const cls =
        level === 1
          ? 'text-base font-bold mt-5 mb-1.5'
          : level === 2
            ? 'text-sm font-semibold mt-4 mb-1'
            : 'text-sm font-medium mt-3 mb-0.5';
      nodes.push(
        <div key={k++} className={cls} style={{ color: colors.textPrimary }}>
          <InlineText text={text} />
        </div>,
      );
      i++;
      continue;
    }

    // Horizontal rule
    if (/^[-*]{3,}$/.test(line.trim())) {
      nodes.push(<hr key={k++} className="my-4" style={{ borderColor: colors.border }} />);
      i++;
      continue;
    }

    // Blockquote
    if (line.startsWith('> ')) {
      nodes.push(
        <blockquote
          key={k++}
          className="pl-3 py-0.5 my-2 text-sm italic"
          style={{ color: colors.textDim, borderLeft: `2px solid ${noteColor}` }}
        >
          <InlineText text={line.slice(2)} />
        </blockquote>,
      );
      i++;
      continue;
    }

    // Unordered list — collect consecutive items
    if (/^[-*+]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*+]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*+]\s+/, ''));
        i++;
      }
      nodes.push(
        <ul key={k++} className="list-disc pl-5 my-2 space-y-0.5">
          {items.map((item, idx) => (
            <li key={idx} className="text-sm leading-relaxed" style={{ color: colors.textMuted }}>
              <InlineText text={item} />
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    // Ordered list — collect consecutive items
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s+/, ''));
        i++;
      }
      nodes.push(
        <ol key={k++} className="list-decimal pl-5 my-2 space-y-0.5">
          {items.map((item, idx) => (
            <li key={idx} className="text-sm leading-relaxed" style={{ color: colors.textMuted }}>
              <InlineText text={item} />
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    // Empty line — skip
    if (line.trim() === '') {
      i++;
      continue;
    }

    // Paragraph
    nodes.push(
      <p key={k++} className="text-sm leading-relaxed my-1.5" style={{ color: colors.textMuted }}>
        <InlineText text={line} />
      </p>,
    );
    i++;
  }

  return <>{nodes}</>;
}

// ── Note metadata ─────────────────────────────────────────────────

interface NoteMetadata {
  tags?: string[];
  aliases?: string[];
  backlinks?: string[];
}

function extractNoteMetadata(chunks: ChunkResponse[]): NoteMetadata {
  const meta: NoteMetadata = {};
  for (const chunk of chunks) {
    const dm = chunk.domain_metadata as Record<string, unknown> | null;
    if (!dm) continue;
    if (!meta.tags && Array.isArray(dm.tags)) meta.tags = dm.tags as string[];
    if (!meta.aliases && Array.isArray(dm.aliases)) meta.aliases = dm.aliases as string[];
    if (!meta.backlinks && Array.isArray(dm.backlinks)) meta.backlinks = dm.backlinks as string[];
  }
  return meta;
}

// ── NoteChunk ─────────────────────────────────────────────────────

function NoteChunk({ chunk, isLast }: { chunk: ChunkResponse; isLast: boolean }): ReactNode {
  return (
    <div id={`chunk-${chunk.chunk_index}`}>
      {/* Breadcrumb from context_header */}
      {chunk.context_header && (
        <div
          className="text-xs font-mono mb-2 leading-tight"
          style={{ color: colors.textDim, opacity: 0.7 }}
        >
          {chunk.context_header}
        </div>
      )}

      {/* Content — code chunks rendered verbatim, prose via dark markdown */}
      {chunk.chunk_type === 'code' ? (
        <pre
          className="overflow-x-auto rounded p-3 text-xs font-mono leading-relaxed"
          style={{ background: colors.bgElevated, color: '#93C5FD', border: `1px solid ${colors.border}` }}
        >
          <code>{chunk.content}</code>
        </pre>
      ) : chunk.chunk_type === 'table' || chunk.chunk_type === 'table_part' ? (
        <pre
          className="overflow-x-auto rounded p-3 text-xs font-mono leading-relaxed"
          style={{ background: colors.bgElevated, color: colors.textMuted, border: `1px solid ${colors.border}` }}
        >
          {chunk.content}
        </pre>
      ) : (
        <DarkMarkdownContent content={chunk.content} />
      )}

      {/* Chunk boundary divider */}
      {!isLast && <div className="mt-4 mb-3" style={{ borderTop: `1px solid ${colors.borderSubtle}` }} />}
    </div>
  );
}

// ── NoteDetail ────────────────────────────────────────────────────

function NoteDetail({ source }: { source: SourceSummary }): ReactNode {
  const { data, isLoading } = useQuery({
    queryKey: ['chunks', source.source_id],
    queryFn: () => fetchSourceChunks(source.source_id),
    staleTime: 30_000,
  });

  const sortedChunks = useMemo(() => {
    if (!data?.chunks) return [];
    return [...data.chunks].sort((a, b) => a.chunk_index - b.chunk_index);
  }, [data]);

  const noteMeta = useMemo(() => extractNoteMetadata(sortedChunks), [sortedChunks]);
  const hasMeta =
    (noteMeta.tags?.length ?? 0) +
      (noteMeta.aliases?.length ?? 0) +
      (noteMeta.backlinks?.length ?? 0) >
    0;

  return (
    <div className="flex flex-col h-full">
      {/* Fixed header */}
      <div
        className="px-6 pt-5 pb-4 shrink-0"
        style={{ borderBottom: `1px solid ${colors.border}` }}
      >
        <h1 className="text-xl font-bold mb-2 leading-tight" style={{ color: colors.textPrimary }}>
          {noteTitle(source)}
        </h1>
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="px-1.5 py-0.5 rounded text-xs font-medium"
            style={{ background: `${noteColor}20`, color: noteColor }}
          >
            {adapterLabel(source.adapter_id)}
          </span>
          <span className="text-xs" style={{ color: colors.textDim }}>
            {source.chunk_count} {source.chunk_count === 1 ? 'chunk' : 'chunks'}
          </span>
          <span className="text-xs" style={{ color: colors.textDim }}>
            ·
          </span>
          <span className="text-xs" style={{ color: colors.textDim }}>
            {timeAgo(source.updated_at)}
          </span>
          {source.origin_ref && (
            <>
              <span className="text-xs" style={{ color: colors.textDim }}>
                ·
              </span>
              <span className="text-xs truncate max-w-xs" style={{ color: colors.textDim }}>
                {source.origin_ref}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Metadata tags/aliases/backlinks — only when present */}
      {!isLoading && hasMeta && (
        <div
          className="px-6 py-3 shrink-0 flex flex-wrap gap-2"
          style={{ borderBottom: `1px solid ${colors.border}` }}
        >
          {noteMeta.tags?.map(tag => (
            <span
              key={tag}
              className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs"
              style={{ background: `${noteColor}18`, color: noteColor }}
            >
              <TagIcon className="w-3 h-3 shrink-0" />
              {tag}
            </span>
          ))}
          {noteMeta.aliases?.map(alias => (
            <span
              key={alias}
              className="px-2 py-0.5 rounded-full text-xs"
              style={{ background: colors.bgElevated, color: colors.textMuted }}
            >
              ~{alias}
            </span>
          ))}
          {noteMeta.backlinks?.map(link => (
            <span
              key={link}
              className="px-2 py-0.5 rounded text-xs"
              style={{ background: colors.bgElevated, color: colors.textDim }}
            >
              ↩ {link}
            </span>
          ))}
        </div>
      )}

      {/* Scrollable content */}
      <div className="flex-1 px-6 py-4 overflow-y-auto">
        {isLoading ? (
          <div className="space-y-3 animate-pulse">
            {[80, 60, 90, 50, 75, 65, 85].map((w, i) => (
              <div
                key={i}
                className="h-3.5 rounded"
                style={{ width: `${w}%`, background: colors.bgElevated }}
              />
            ))}
          </div>
        ) : sortedChunks.length === 0 ? (
          <p className="text-sm" style={{ color: colors.textDim }}>
            No content available.
          </p>
        ) : (
          sortedChunks.map((chunk, idx) => (
            <NoteChunk
              key={chunk.chunk_hash}
              chunk={chunk}
              isLast={idx === sortedChunks.length - 1}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ── NoteCard ──────────────────────────────────────────────────────

function NoteCard({
  source,
  isSelected,
  onClick,
}: {
  source: SourceSummary;
  isSelected: boolean;
  onClick: () => void;
}): ReactNode {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-3 transition-colors"
      style={{
        background: isSelected ? `${noteColor}18` : 'transparent',
        borderLeft: `2px solid ${isSelected ? noteColor : 'transparent'}`,
      }}
    >
      <div className="flex items-start justify-between gap-2 mb-1">
        <span
          className="text-sm font-medium leading-snug line-clamp-2"
          style={{ color: isSelected ? colors.textPrimary : colors.textMuted }}
        >
          {noteTitle(source)}
        </span>
        <span className="text-xs shrink-0 mt-0.5" style={{ color: colors.textDim }}>
          {timeAgo(source.updated_at)}
        </span>
      </div>
      <div className="flex items-center gap-2 min-w-0">
        <span
          className="text-xs px-1.5 py-0.5 rounded shrink-0"
          style={{ background: `${noteColor}18`, color: noteColor }}
        >
          {adapterLabel(source.adapter_id)}
        </span>
        <span className="text-xs truncate" style={{ color: colors.textDim }}>
          {source.origin_ref}
        </span>
      </div>
    </button>
  );
}

// ── AdapterGroup ──────────────────────────────────────────────────

function AdapterGroup({
  adapterId,
  sources,
  selectedSourceId,
  isAdapterActive,
  onSelect,
  onAdapterClick,
}: {
  adapterId: string;
  sources: SourceSummary[];
  selectedSourceId: string | null;
  isAdapterActive: boolean;
  onSelect: (sourceId: string) => void;
  onAdapterClick: () => void;
}): ReactNode {
  return (
    <div className="mb-1">
      {/* Adapter header — clickable to filter/clear center panel */}
      <button
        onClick={onAdapterClick}
        className="w-full px-3 py-1.5 flex items-center gap-1.5 transition-colors"
        style={{ background: isAdapterActive ? `${noteColor}10` : 'transparent' }}
        title={isAdapterActive ? 'Click to clear filter' : `Filter by ${adapterLabel(adapterId)}`}
      >
        <ChevronDownIcon
          className="w-3 h-3 shrink-0"
          style={{ color: isAdapterActive ? noteColor : colors.textDim }}
        />
        <span
          className="text-xs font-semibold uppercase tracking-wide"
          style={{ color: isAdapterActive ? noteColor : colors.textDim }}
        >
          {adapterLabel(adapterId)}
        </span>
        <span className="text-xs ml-auto tabular-nums" style={{ color: colors.textDim }}>
          {sources.length}
        </span>
      </button>

      {/* Note entries */}
      {sources.map(source => {
        const isSelected = source.source_id === selectedSourceId;
        return (
          <button
            key={source.source_id}
            onClick={() => onSelect(source.source_id)}
            className="w-full text-left pl-7 pr-3 py-1 text-xs leading-snug truncate block transition-colors"
            title={noteTitle(source)}
            style={{
              color: isSelected ? noteColor : colors.textMuted,
              background: isSelected ? `${noteColor}12` : 'transparent',
            }}
          >
            {noteTitle(source)}
          </button>
        );
      })}
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────

function EmptyDetail(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 48, height: 48, background: `${noteColor}20` }}
      >
        <svg
          className="w-6 h-6"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          style={{ color: noteColor }}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
      </div>
      <p className="text-sm" style={{ color: colors.textDim }}>
        Select a note to read
      </p>
    </div>
  );
}

// ── NotesPage ─────────────────────────────────────────────────────

export default function NotesPage(): ReactNode {
  const navigate = useNavigate();
  const { source_id: selectedSourceId, adapter: activeAdapter } = useSearch({ from: '/notes' });
  const [filterText, setFilterText] = useState('');

  const sourcesQuery = useSources({ domain: 'notes', limit: 500 });
  const sources = sourcesQuery.data?.sources ?? [];

  // Group by adapter prefix for the folder tree
  const adapterGroups = useMemo(() => {
    const groups = new Map<string, SourceSummary[]>();
    for (const source of sources) {
      const prefix = adapterPrefix(source.adapter_id);
      if (!groups.has(prefix)) groups.set(prefix, []);
      groups.get(prefix)!.push(source);
    }
    // Sort each group alphabetically by title
    for (const items of groups.values()) {
      items.sort((a, b) => noteTitle(a).localeCompare(noteTitle(b)));
    }
    return groups;
  }, [sources]);

  // Center panel: apply adapter filter + text search, sorted by recency
  const filteredSources = useMemo(() => {
    let list = sources;
    if (activeAdapter) {
      list = list.filter(s => adapterPrefix(s.adapter_id) === activeAdapter);
    }
    if (filterText.trim()) {
      const q = filterText.toLowerCase();
      list = list.filter(
        s =>
          noteTitle(s).toLowerCase().includes(q) ||
          s.origin_ref.toLowerCase().includes(q),
      );
    }
    return [...list].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
  }, [sources, activeAdapter, filterText]);

  const selectedSource = useMemo(
    () => sources.find(s => s.source_id === selectedSourceId) ?? null,
    [sources, selectedSourceId],
  );

  function selectSource(sourceId: string): void {
    void navigate({
      to: '/notes',
      search: { source_id: sourceId, adapter: activeAdapter },
    });
  }

  function selectAdapter(prefix: string): void {
    // Toggle: clicking the active adapter clears the filter
    const next = activeAdapter === prefix ? undefined : prefix;
    void navigate({
      to: '/notes',
      search: { source_id: selectedSourceId, adapter: next },
    });
  }

  return (
    <div className="flex h-full overflow-hidden" style={{ background: colors.bgBase }}>

      {/* ── Left panel: vault / folder tree ── */}
      <div
        className="w-48 shrink-0 flex flex-col overflow-y-auto"
        style={{ borderRight: `1px solid ${colors.border}`, background: colors.bgSidebar }}
      >
        <div className="px-3 py-3 shrink-0">
          <span
            className="text-xs font-semibold uppercase tracking-wider"
            style={{ color: colors.textDim }}
          >
            Vaults
          </span>
        </div>

        {sourcesQuery.isLoading ? (
          <div className="px-3 py-2 space-y-2">
            {[60, 80, 50, 70, 90].map((w, i) => (
              <div
                key={i}
                className="h-3 rounded animate-pulse"
                style={{ width: `${w}%`, background: colors.bgElevated }}
              />
            ))}
          </div>
        ) : adapterGroups.size === 0 ? (
          <div className="px-3 py-2 text-xs" style={{ color: colors.textDim }}>
            No notes found
          </div>
        ) : (
          Array.from(adapterGroups.entries()).map(([prefix, groupSources]) => (
            <AdapterGroup
              key={prefix}
              adapterId={groupSources[0].adapter_id}
              sources={groupSources}
              selectedSourceId={selectedSourceId ?? null}
              isAdapterActive={activeAdapter === prefix}
              onSelect={selectSource}
              onAdapterClick={() => selectAdapter(prefix)}
            />
          ))
        )}
      </div>

      {/* ── Center panel: note list ── */}
      <div
        className="w-72 shrink-0 flex flex-col overflow-hidden"
        style={{ borderRight: `1px solid ${colors.border}`, background: colors.bgSurface }}
      >
        {/* Filter bar */}
        <div className="px-3 py-2 shrink-0" style={{ borderBottom: `1px solid ${colors.border}` }}>
          <div
            className="flex items-center gap-2 px-2 py-1.5 rounded"
            style={{ background: colors.bgElevated }}
          >
            <MagnifyingGlassIcon
              className="w-3.5 h-3.5 shrink-0"
              style={{ color: colors.textDim }}
            />
            <input
              type="text"
              value={filterText}
              onChange={e => setFilterText(e.target.value)}
              placeholder="Filter notes…"
              className="flex-1 bg-transparent text-xs outline-none"
              style={{ color: colors.textPrimary }}
            />
          </div>
        </div>

        {/* Count line + active adapter badge */}
        <div className="px-4 py-1.5 shrink-0 flex items-center gap-2">
          <span className="text-xs" style={{ color: colors.textDim }}>
            {filteredSources.length}{' '}
            {filteredSources.length === 1 ? 'note' : 'notes'}
          </span>
          {activeAdapter && (
            <button
              onClick={() => selectAdapter(activeAdapter)}
              className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs transition-opacity hover:opacity-70"
              style={{ background: `${noteColor}20`, color: noteColor }}
              title="Clear adapter filter"
            >
              {adapterLabel(activeAdapter)}
              <span className="text-xs leading-none">×</span>
            </button>
          )}
        </div>

        {/* Scrollable note list */}
        <div className="flex-1 overflow-y-auto">
          {sourcesQuery.isLoading ? (
            <div className="px-4 py-2 space-y-4">
              {[1, 2, 3, 4, 5].map(i => (
                <div key={i} className="space-y-1.5 animate-pulse">
                  <div
                    className="h-3 rounded"
                    style={{ width: '70%', background: colors.bgElevated }}
                  />
                  <div
                    className="h-2.5 rounded"
                    style={{ width: '50%', background: colors.bgElevated }}
                  />
                </div>
              ))}
            </div>
          ) : filteredSources.length === 0 ? (
            <div className="px-4 py-6 text-center">
              <p className="text-xs" style={{ color: colors.textDim }}>
                {filterText ? 'No notes match your filter' : 'No notes available'}
              </p>
            </div>
          ) : (
            filteredSources.map(source => (
              <NoteCard
                key={source.source_id}
                source={source}
                isSelected={source.source_id === selectedSourceId}
                onClick={() => selectSource(source.source_id)}
              />
            ))
          )}
        </div>
      </div>

      {/* ── Right panel: note detail ── */}
      <div className="flex-1 min-w-0 overflow-hidden" style={{ background: colors.bgBase }}>
        {selectedSource ? <NoteDetail source={selectedSource} /> : <EmptyDetail />}
      </div>
    </div>
  );
}
