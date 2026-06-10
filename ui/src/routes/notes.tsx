import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState, useRef, useCallback, useEffect } from 'react';
import type { ReactNode } from 'react';
import { Chip, SplitPane, Icon, PageHeader } from '@tinkermonkey/heimdall-ui';
import { HierarchyTree } from '../components/HierarchyTree';
import { OutlinePanel } from '../components/OutlinePanel';
import { FilterDropdown } from '../components/FilterDropdown';
import type { TreeNode } from '../components/HierarchyTree';
import type { OutlineItem } from '../components/OutlinePanel';
import { useSources } from '../hooks/useSources';
import { fetchSourceChunks } from '../api/client';
import { getDomainColor, getDomainColorWithAlpha } from '../lib/designTokens';
import type { SourceSummary, ChunkResponse } from '../types/api';

const noteColor = getDomainColor('notes');

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

/** Convert a heading text to a stable HTML id (slug). */
function slugify(text: string, index: number): string {
  return `heading-${index}-${text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`;
}

// ── Build HierarchyTree nodes from sources ─────────────────────────

function buildTreeNodes(sources: SourceSummary[], adapterFilter: string[]): TreeNode[] {
  const byAdapter = new Map<string, SourceSummary[]>();
  for (const source of sources) {
    const prefix = adapterPrefix(source.adapter_id);
    if (adapterFilter.length > 0 && !adapterFilter.includes(prefix)) continue;
    if (!byAdapter.has(prefix)) byAdapter.set(prefix, []);
    byAdapter.get(prefix)!.push(source);
  }

  return Array.from(byAdapter.entries()).map(([prefix, groupSources]) => {
    const sorted = [...groupSources].sort((a, b) => noteTitle(a).localeCompare(noteTitle(b)));
    return {
      id:    `adapter:${prefix}`,
      label: adapterLabel(groupSources[0].adapter_id),
      type:  'folder' as const,
      badge: String(sorted.length),
      children: sorted.map(source => ({
        id:    source.source_id,
        label: noteTitle(source),
        type:  'file' as const,
        data:  source,
      })),
    };
  });
}

// ── Extract outline items from chunks ─────────────────────────────

function extractOutlineItems(chunks: ChunkResponse[]): OutlineItem[] {
  const items: OutlineItem[] = [];
  let headingIndex = 0;
  for (const chunk of chunks) {
    const lines = chunk.content.split('\n');
    for (const line of lines) {
      const match = line.match(/^(#{1,6})\s+(.+)$/);
      if (match) {
        const level = match[1].length as OutlineItem['level'];
        const label = match[2];
        const id = slugify(label, headingIndex++);
        items.push({ id, label, level });
      }
    }
  }
  return items;
}

// ── Inline text renderer ──────────────────────────────────────────

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
            <strong key={i} className="font-semibold" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
              {part.content}
            </strong>
          );
        }
        if (part.type === 'code') {
          return (
            <code
              key={i}
              className="px-1 rounded text-xs font-mono"
              style={{ background: 'rgb(var(--canvas-surface))', color: '#93C5FD' }}
            >
              {part.content}
            </code>
          );
        }
        if (part.type === 'wikilink') {
          return (
            <Chip
              key={i}
              className="text-xs"
              style={{ color: noteColor, background: getDomainColorWithAlpha('notes', '20') }}
            >
              {part.content}
            </Chip>
          );
        }
        return <span key={i}>{part.content}</span>;
      })}
    </>
  );
}

// ── Markdown renderer with heading IDs for scroll targeting ───────

interface MarkdownRendererProps {
  content: string;
  /** Global counter offset so heading IDs are unique across chunks. */
  headingOffset: number;
}

function DarkMarkdownContent({ content, headingOffset }: MarkdownRendererProps): ReactNode {
  const lines = content.split('\n');
  const nodes: ReactNode[] = [];
  let i = 0;
  let k = 0;
  let headingCount = headingOffset;

  while (i < lines.length) {
    const line = lines[i];

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
          style={{ background: 'rgb(var(--canvas-surface))', color: '#93C5FD', border: `1px solid rgb(var(--canvas-border))` }}
        >
          <code>{codeLines.join('\n')}</code>
        </pre>,
      );
      i++;
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const id = slugify(text, headingCount++);
      const cls =
        level === 1
          ? 'text-base font-bold mt-5 mb-1.5'
          : level === 2
            ? 'text-sm font-semibold mt-4 mb-1'
            : 'text-sm font-medium mt-3 mb-0.5';
      nodes.push(
        <div key={k++} id={id} className={cls} style={{ color: 'rgb(var(--canvas-fg-1))' }}>
          <InlineText text={text} />
        </div>,
      );
      i++;
      continue;
    }

    if (/^[-*]{3,}$/.test(line.trim())) {
      nodes.push(<hr key={k++} className="my-4" style={{ borderColor: 'rgb(var(--canvas-border))' }} />);
      i++;
      continue;
    }

    if (line.startsWith('> ')) {
      nodes.push(
        <blockquote
          key={k++}
          className="pl-3 py-0.5 my-2 text-sm italic"
          style={{ color: 'rgb(var(--canvas-fg-3))', borderLeft: `2px solid ${noteColor}` }}
        >
          <InlineText text={line.slice(2)} />
        </blockquote>,
      );
      i++;
      continue;
    }

    if (/^[-*+]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*+]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*+]\s+/, ''));
        i++;
      }
      nodes.push(
        <ul key={k++} className="list-disc pl-5 my-2 space-y-0.5">
          {items.map((item, idx) => (
            <li key={idx} className="text-sm leading-relaxed" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
              <InlineText text={item} />
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s+/, ''));
        i++;
      }
      nodes.push(
        <ol key={k++} className="list-decimal pl-5 my-2 space-y-0.5">
          {items.map((item, idx) => (
            <li key={idx} className="text-sm leading-relaxed" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
              <InlineText text={item} />
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    if (line.trim() === '') {
      i++;
      continue;
    }

    nodes.push(
      <p key={k++} className="text-sm leading-relaxed my-1.5" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
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

// ── Chunk boundary marker ─────────────────────────────────────────

function ChunkBoundary({ index, total }: { index: number; total: number }): ReactNode {
  return (
    <div
      className="flex items-center gap-2 my-3"
      title={`Chunk ${index + 1} of ${total}`}
    >
      <div className="flex-1 h-px" style={{ background: `${noteColor}33` }} />
      <span
        className="text-xs px-1.5 py-0.5 rounded font-mono shrink-0"
        style={{
          color: noteColor,
          background: getDomainColorWithAlpha('notes', '12'),
          fontSize: 9,
        }}
      >
        chunk {index + 1}
      </span>
      <div className="flex-1 h-px" style={{ background: `${noteColor}33` }} />
    </div>
  );
}

// ── NoteContentPanel ──────────────────────────────────────────────

function NoteContentPanel({
  source,
  scrollRef,
  onOutlineChange,
}: {
  source: SourceSummary;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  onOutlineChange: (items: OutlineItem[]) => void;
}): ReactNode {
  const { data, isLoading, isError } = useQuery({
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
      (noteMeta.backlinks?.length ?? 0) > 0;

  // Update outline items whenever chunks change
  const outlineItems = useMemo(() => extractOutlineItems(sortedChunks), [sortedChunks]);

  // Report outline to parent for the OutlinePanel
  useEffect(() => {
    onOutlineChange(outlineItems);
  }, [outlineItems, onOutlineChange]);

  // Track cumulative heading count per chunk for correct IDs
  const headingOffsets = useMemo(() => {
    const offsets: number[] = [];
    let count = 0;
    for (const chunk of sortedChunks) {
      offsets.push(count);
      const lines = chunk.content.split('\n');
      for (const line of lines) {
        if (/^#{1,6}\s/.test(line)) count++;
      }
    }
    return offsets;
  }, [sortedChunks]);

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      {/* Fixed header */}
      <div
        className="px-6 pt-5 pb-4 shrink-0"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        <h1 className="text-xl font-bold mb-2 leading-tight" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
          {noteTitle(source)}
        </h1>
        <div className="flex items-center gap-2 flex-wrap">
          <Chip
            className="text-xs font-medium"
            style={{ background: getDomainColorWithAlpha('notes', '20'), color: noteColor }}
          >
            {adapterLabel(source.adapter_id)}
          </Chip>
          <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            {source.chunk_count} {source.chunk_count === 1 ? 'chunk' : 'chunks'}
          </span>
          <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>·</span>
          <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            {timeAgo(source.updated_at)}
          </span>
        </div>
      </div>

      {/* Metadata tags/aliases/backlinks */}
      {!isLoading && hasMeta && (
        <div
          className="px-6 py-3 shrink-0 flex flex-wrap gap-2"
          style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
        >
          {noteMeta.tags?.map(tag => (
            <Chip
              key={tag}
              className="flex items-center gap-1 text-xs"
              style={{ background: getDomainColorWithAlpha('notes', '18'), color: noteColor }}
            >
              <Icon name="filter" size={12} className="shrink-0" />
              {tag}
            </Chip>
          ))}
          {noteMeta.aliases?.map(alias => (
            <span
              key={alias}
              className="px-2 py-0.5 rounded-full text-xs"
              style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-2))' }}
            >
              ~{alias}
            </span>
          ))}
          {noteMeta.backlinks?.map(link => (
            <span
              key={link}
              className="px-2 py-0.5 rounded text-xs"
              style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-3))' }}
            >
              ↩ {link}
            </span>
          ))}
        </div>
      )}

      {/* Scrollable content with chunk boundaries */}
      <div ref={scrollRef} className="flex-1 px-6 py-4 overflow-y-auto">
        {isLoading ? (
          <div className="space-y-3 animate-pulse">
            {[80, 60, 90, 50, 75, 65, 85].map((w, i) => (
              <div
                key={i}
                className="h-3.5 rounded"
                style={{ width: `${w}%`, background: 'rgb(var(--canvas-surface))' }}
              />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <span style={{ color: 'rgb(var(--status-error))' }}>
              <Icon name="alert" size={32} />
            </span>
            <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              Failed to load note content.
            </p>
          </div>
        ) : sortedChunks.length === 0 ? (
          <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            No content available.
          </p>
        ) : (
          sortedChunks.map((chunk, idx) => (
            <div key={chunk.chunk_hash}>
              {/* Chunk boundary marker between chunks */}
              {idx > 0 && <ChunkBoundary index={idx} total={sortedChunks.length} />}

              {/* Context header breadcrumb */}
              {chunk.context_header && (
                <div
                  className="text-xs font-mono mb-2 leading-tight"
                  style={{ color: 'rgb(var(--canvas-fg-3))', opacity: 0.7 }}
                >
                  {chunk.context_header}
                </div>
              )}

              {/* Chunk content */}
              {chunk.chunk_type === 'code' ? (
                <pre
                  className="overflow-x-auto rounded p-3 text-xs font-mono leading-relaxed"
                  style={{ background: 'rgb(var(--canvas-surface))', color: '#93C5FD', border: `1px solid rgb(var(--canvas-border))` }}
                >
                  <code>{chunk.content}</code>
                </pre>
              ) : chunk.chunk_type === 'table' || chunk.chunk_type === 'table_part' ? (
                <pre
                  className="overflow-x-auto rounded p-3 text-xs font-mono leading-relaxed"
                  style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-2))', border: `1px solid rgb(var(--canvas-border))` }}
                >
                  {chunk.content}
                </pre>
              ) : (
                <DarkMarkdownContent content={chunk.content} headingOffset={headingOffsets[idx] ?? 0} />
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ── Empty detail ──────────────────────────────────────────────────

function EmptyDetail(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 48, height: 48, background: getDomainColorWithAlpha('notes', '20') }}
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
      <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
        Select a note to read
      </p>
    </div>
  );
}

// ── NotesPage ─────────────────────────────────────────────────────

export default function NotesPage(): ReactNode {
  const navigate = useNavigate();
  const { source_id: selectedSourceId, adapter: activeAdapters } = useSearch({ from: '/notes' });

  const sourcesQuery = useSources({ domain: 'notes', limit: 500 });
  const sources = useMemo(() => sourcesQuery.data?.sources ?? [], [sourcesQuery.data]);

  // Collect unique adapter prefixes for filter dropdown
  const adapterPrefixes = useMemo(() => {
    const set = new Set<string>();
    for (const s of sources) set.add(adapterPrefix(s.adapter_id));
    return Array.from(set).sort();
  }, [sources]);

  // activeAdapters is stored as comma-separated string in URL
  const activeAdapterList = useMemo(() => {
    if (!activeAdapters) return [];
    return activeAdapters.split(',').filter(Boolean);
  }, [activeAdapters]);

  function setAdapterFilters(values: string[]): void {
    void navigate({
      to: '/notes',
      search: { source_id: selectedSourceId, adapter: values.length > 0 ? values.join(',') : undefined },
    });
  }

  const treeNodes = useMemo(
    () => buildTreeNodes(sources, activeAdapterList),
    [sources, activeAdapterList],
  );

  // Adapter folders default to expanded. Track only folders the user has explicitly collapsed.
  const [collapsedByUser, setCollapsedByUser] = useState<Set<string>>(new Set());

  // Effective expanded set: all adapter folders are open by default, minus any user-collapsed
  const expandedIds = useMemo(() => {
    const ids = new Set<string>();
    for (const s of sources) {
      const folderId = `adapter:${adapterPrefix(s.adapter_id)}`;
      if (!collapsedByUser.has(folderId)) ids.add(folderId);
    }
    return ids;
  }, [sources, collapsedByUser]);

  function handleExpandToggle(id: string): void {
    setCollapsedByUser(prev => {
      const next = new Set(prev);
      // If folder is currently expanded (not in collapsed set), collapse it; otherwise expand it
      if (!prev.has(id)) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function selectSource(sourceId: string): void {
    void navigate({
      to: '/notes',
      search: { source_id: sourceId, adapter: activeAdapters },
    });
  }

  const selectedSource = useMemo(
    () => sources.find(s => s.source_id === selectedSourceId) ?? null,
    [sources, selectedSourceId],
  );

  // Outline items derived from the selected note's chunks
  const [outlineItems, setOutlineItems] = useState<OutlineItem[]>([]);
  const [activeOutlineId, setActiveOutlineId] = useState<string | undefined>(undefined);

  const contentScrollRef = useRef<HTMLDivElement>(null);

  const handleOutlineClick = useCallback((item: OutlineItem) => {
    setActiveOutlineId(item.id);
    const container = contentScrollRef.current;
    if (!container) return;
    const el = container.querySelector<HTMLElement>(`#${CSS.escape(item.id)}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, []);

  const adapterFilterSummary = activeAdapterList.length > 0
    ? `${activeAdapterList.length} selected`
    : 'All';

  // Left: HierarchyTree pane
  const treePanel = (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: 'rgb(var(--canvas-surface))' }}
    >
      {/* Tree header + FilterDropdown */}
      <div
        className="px-3 py-2 shrink-0 flex items-center gap-2"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        <span
          className="text-xs font-semibold uppercase tracking-wider flex-1"
          style={{ color: 'rgb(var(--canvas-fg-3))' }}
        >
          Notes
        </span>
        {adapterPrefixes.length > 1 && (
          <FilterDropdown
            mode="checkbox"
            value={activeAdapterList}
            onChange={setAdapterFilters}
          >
            <FilterDropdown.Trigger label="Adapter" summary={adapterFilterSummary} />
            <FilterDropdown.Panel>
              <FilterDropdown.Section title="Source adapter">
                {adapterPrefixes.map(prefix => (
                  <FilterDropdown.Checkbox
                    key={prefix}
                    value={prefix}
                    label={prefix.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                  />
                ))}
              </FilterDropdown.Section>
            </FilterDropdown.Panel>
          </FilterDropdown>
        )}
      </div>

      {/* Tree content */}
      <div className="flex-1 overflow-y-auto py-1">
        {sourcesQuery.isLoading ? (
          <div className="px-3 py-2 space-y-2">
            {[60, 80, 50, 70, 90].map((w, i) => (
              <div
                key={i}
                className="h-3 rounded animate-pulse"
                style={{ width: `${w}%`, background: 'rgb(var(--canvas-bg-2))' }}
              />
            ))}
          </div>
        ) : sourcesQuery.isError ? (
          <div className="px-3 py-3 text-center">
            <div className="flex justify-center mb-2" style={{ color: 'rgb(var(--status-error))' }}>
              <Icon name="alert" size={20} />
            </div>
            <p className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Failed to load notes</p>
          </div>
        ) : treeNodes.length === 0 ? (
          <div className="px-3 py-2 text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            No notes found
          </div>
        ) : (
          <HierarchyTree
            nodes={treeNodes}
            selectedId={selectedSourceId ?? null}
            expandedIds={expandedIds}
            onExpandToggle={handleExpandToggle}
            onSelect={node => {
              if (node.type === 'file') selectSource(node.id);
            }}
          />
        )}
      </div>
    </div>
  );

  // Center: Note content pane
  const contentPanel = (
    <div className="h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      {selectedSource ? (
        <NoteContentPanel
          source={selectedSource}
          scrollRef={contentScrollRef}
          onOutlineChange={setOutlineItems}
        />
      ) : (
        <EmptyDetail />
      )}
    </div>
  );

  // Right: Outline pane
  const outlinePanel = (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: 'rgb(var(--canvas-surface))' }}
    >
      <div
        className="px-3 py-2 shrink-0"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        <span
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: 'rgb(var(--canvas-fg-3))' }}
        >
          Outline
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {outlineItems.length > 0 ? (
          <OutlinePanel
            items={outlineItems}
            activeId={activeOutlineId}
            onItemClick={handleOutlineClick}
          />
        ) : (
          <div className="px-3 py-4">
            <p className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              {selectedSource ? 'No headings found' : 'Select a note'}
            </p>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Domains"
        title="Notes"
        subtitle="Browse notes from Obsidian and Apple Notes"
      />
      <div className="flex-1 min-h-0 overflow-hidden">
        <SplitPane
          direction="horizontal"
          initialSplitPercent={22}
          minSize={180}
          first={treePanel}
          second={
            <SplitPane
              direction="horizontal"
              initialSplitPercent={75}
              minSize={250}
              first={contentPanel}
              second={outlinePanel}
            />
          }
        />
      </div>
    </div>
  );
}
