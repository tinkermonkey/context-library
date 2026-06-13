import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  HomeIcon,
  ArrowsUpDownIcon,
  ListBulletIcon,
  Squares2X2Icon,
} from '@heroicons/react/24/outline';
import {
  Icon, PageHeader,
  SplitPane,
  HierarchyTree, HierarchyRow,
  AssetCard, AssetGrid,
} from '@tinkermonkey/heimdall-ui';
import { FilterDropdown } from '../components/FilterDropdown';
import { useSources } from '../hooks/useSources';
import { fetchSourceChunks } from '../api/client';
import { getDomainColor, getDomainColorWithAlpha } from '../lib/designTokens';
import type { SourceSummary, ChunkResponse } from '../types/api';
import { extractDocumentMetadata } from '../types/api';

const docColor = getDomainColor('documents');

// ── Helpers ───────────────────────────────────────────────────────

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function getFilename(originRef: string): string {
  return originRef.split('/').pop() ?? originRef;
}

function getExtension(filename: string): string {
  const dot = filename.lastIndexOf('.');
  return dot >= 0 ? filename.slice(dot + 1).toLowerCase() : '';
}

type FileCategory = 'pdf' | 'text' | 'code' | 'image' | 'archive' | 'spreadsheet' | 'video' | 'audio' | 'other';

function categorizeFile(originRef: string): FileCategory {
  const ext = getExtension(getFilename(originRef));
  if (['pdf'].includes(ext)) return 'pdf';
  if (['md', 'txt', 'rst', 'org', 'rtf', 'doc', 'docx'].includes(ext)) return 'text';
  if (['js', 'ts', 'tsx', 'jsx', 'py', 'go', 'rs', 'java', 'c', 'cpp', 'h', 'sh', 'yaml', 'yml', 'json', 'toml', 'css', 'html', 'xml', 'sql'].includes(ext)) return 'code';
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico'].includes(ext)) return 'image';
  if (['zip', 'tar', 'gz', 'bz2', 'rar', '7z'].includes(ext)) return 'archive';
  if (['csv', 'xlsx', 'xls', 'ods', 'tsv'].includes(ext)) return 'spreadsheet';
  if (['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext)) return 'video';
  if (['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg'].includes(ext)) return 'audio';
  return 'other';
}

// ── Path utilities ────────────────────────────────────────────────

/**
 * Parse all source origin_refs to extract a normalized directory tree.
 * Returns a Map of folder path → list of sources in that folder.
 */
function buildFolderTree(sources: SourceSummary[]): Map<string, SourceSummary[]> {
  const tree = new Map<string, SourceSummary[]>();
  tree.set('', []);

  for (const source of sources) {
    const parts = source.origin_ref.replace(/^\/+/, '').split('/').filter(Boolean);
    if (parts.length === 0) continue;

    const parentParts = parts.slice(0, -1);
    const parentPath = parentParts.join('/');
    if (!tree.has(parentPath)) tree.set(parentPath, []);
    tree.get(parentPath)!.push(source);

    for (let i = 1; i < parentParts.length; i++) {
      const ancestorPath = parentParts.slice(0, i).join('/');
      if (!tree.has(ancestorPath)) tree.set(ancestorPath, []);
    }
  }

  return tree;
}

function getSubfolders(tree: Map<string, SourceSummary[]>, folderPath: string): string[] {
  const prefix = folderPath ? folderPath + '/' : '';
  const subs = new Set<string>();
  for (const key of tree.keys()) {
    if (key === folderPath) continue;
    if (key.startsWith(prefix)) {
      const remainder = key.slice(prefix.length);
      const nextSegment = remainder.split('/')[0];
      if (nextSegment) subs.add(nextSegment);
    }
  }
  return Array.from(subs).sort();
}

function countFilesUnder(tree: Map<string, SourceSummary[]>, folderPath: string): number {
  let count = 0;
  const prefix = folderPath ? folderPath + '/' : '';
  for (const [key, sources] of tree.entries()) {
    if (key === folderPath || (folderPath !== '' && key.startsWith(prefix))) {
      count += sources.length;
    }
  }
  return count;
}

// ── Sort utilities ────────────────────────────────────────────────

type SortKey = 'name' | 'date' | 'size' | 'type';

function sortSources(sources: SourceSummary[], sortKey: SortKey): SourceSummary[] {
  return [...sources].sort((a, b) => {
    switch (sortKey) {
      case 'name':
        return getFilename(a.origin_ref).localeCompare(getFilename(b.origin_ref));
      case 'date':
        return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
      case 'size':
        return b.chunk_count - a.chunk_count;
      case 'type': {
        const extA = getExtension(getFilename(a.origin_ref));
        const extB = getExtension(getFilename(b.origin_ref));
        return extA.localeCompare(extB);
      }
      default: return 0;
    }
  });
}

// ── Folder tree item (recursive) ──────────────────────────────────

function FolderTreeItem({
  name,
  fullPath,
  tree,
  selectedFolder,
  depth,
  onSelect,
}: {
  name: string;
  fullPath: string;
  tree: Map<string, SourceSummary[]>;
  selectedFolder: string;
  depth: number;
  onSelect: (path: string) => void;
}): ReactNode {
  const subfolders = getSubfolders(tree, fullPath);
  const fileCount = countFilesUnder(tree, fullPath);
  const isSelected = selectedFolder === fullPath;
  const isAncestor = selectedFolder.startsWith(fullPath + '/') && fullPath !== '';
  const isOpen = isSelected || isAncestor;

  return (
    <>
      <HierarchyRow
        depth={depth}
        domain="software"
        kind="taxonomy"
        label={name}
        meta={String(fileCount)}
        selected={isSelected}
        onSelect={() => onSelect(fullPath)}
        showKind={false}
      />
      {isOpen && subfolders.map(sub => (
        <FolderTreeItem
          key={sub}
          name={sub}
          fullPath={fullPath ? `${fullPath}/${sub}` : sub}
          tree={tree}
          selectedFolder={selectedFolder}
          depth={depth + 1}
          onSelect={onSelect}
        />
      ))}
    </>
  );
}

// ── FileRow (list view) ───────────────────────────────────────────

function FileRow({
  source,
  isSelected,
  onClick,
}: {
  source: SourceSummary;
  isSelected: boolean;
  onClick: () => void;
}): ReactNode {
  const filename = getFilename(source.origin_ref);
  const ext = getExtension(filename).toUpperCase() || 'FILE';

  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-2 transition-colors text-left"
      style={{
        background: isSelected ? getDomainColorWithAlpha('documents', '18') : 'transparent',
        borderLeft: `2px solid ${isSelected ? docColor : 'transparent'}`,
      }}
    >
      <span
        className="shrink-0 text-[10px] font-mono px-1 rounded"
        style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-3))' }}
      >
        {ext}
      </span>
      <span
        className="flex-1 text-xs truncate"
        style={{ color: isSelected ? 'rgb(var(--canvas-fg-1))' : 'rgb(var(--canvas-fg-2))' }}
      >
        {filename}
      </span>
      <span className="text-[10px] shrink-0 w-20 text-right" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
        {formatDate(source.updated_at)}
      </span>
      <span className="text-[10px] shrink-0 w-16 text-right" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
        {source.chunk_count} {source.chunk_count === 1 ? 'chunk' : 'chunks'}
      </span>
    </button>
  );
}

// ── FileDetail (preview panel) ────────────────────────────────────

function MetaRow({ label, value }: { label: string; value: string }): ReactNode {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-[10px] w-16 shrink-0" style={{ color: 'rgb(var(--canvas-fg-3))' }}>{label}</span>
      <span className="text-[11px] truncate" style={{ color: 'rgb(var(--canvas-fg-2))' }}>{value}</span>
    </div>
  );
}

function FileDetail({ source }: { source: SourceSummary }): ReactNode {
  const filename = getFilename(source.origin_ref);
  const ext = getExtension(filename).toUpperCase() || 'FILE';

  const chunksQuery = useQuery({
    queryKey: ['chunks', source.source_id],
    queryFn: () => fetchSourceChunks(source.source_id),
    staleTime: 30_000,
  });

  const chunks: ChunkResponse[] = useMemo(() => {
    if (!chunksQuery.data?.chunks) return [];
    return [...chunksQuery.data.chunks].sort((a, b) => a.chunk_index - b.chunk_index);
  }, [chunksQuery.data]);

  const docMeta = useMemo(() => {
    const first = chunks[0];
    if (!first?.domain_metadata) return null;
    try { return extractDocumentMetadata(first.domain_metadata); } catch {
      return null;
    }
  }, [chunks]);

  const contentPreview = useMemo(() => {
    const textChunk = chunks.find(c => c.chunk_type === 'text' || c.chunk_type === 'document');
    if (!textChunk) return chunks[0]?.content ?? null;
    return textChunk.content.slice(0, 500);
  }, [chunks]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 shrink-0" style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}>
        <div
          className="flex items-center justify-center rounded-xl mb-3"
          style={{ width: 48, height: 48, background: getDomainColorWithAlpha('documents', '20') }}
        >
          <span style={{ color: docColor, fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700 }}>
            {ext.slice(0, 4)}
          </span>
        </div>
        <h2 className="text-sm font-semibold leading-snug mb-1" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
          {filename}
        </h2>
        <p className="text-[10px] break-all" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          {source.origin_ref}
        </p>
      </div>

      {/* Metadata */}
      <div className="px-5 py-4 shrink-0 space-y-3" style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}>
        <p className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          File Info
        </p>
        <div className="space-y-2">
          <MetaRow label="Type" value={ext} />
          {docMeta?.file_size_bytes != null && (
            <MetaRow label="Size" value={formatBytes(docMeta.file_size_bytes)} />
          )}
          <MetaRow label="Chunks" value={String(source.chunk_count)} />
          <MetaRow label="Modified" value={formatDate(source.updated_at)} />
          {docMeta?.modified_at && (
            <MetaRow label="File date" value={formatDate(docMeta.modified_at)} />
          )}
          <MetaRow label="Source" value={source.adapter_id.split(':')[0].replace(/_/g, ' ')} />
        </div>
      </div>

      {/* Content preview */}
      <div className="px-5 py-4 shrink-0" style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}>
        <p className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          Preview
        </p>
        {chunksQuery.isLoading ? (
          <div className="space-y-1.5 animate-pulse">
            {[80, 65, 90, 55, 70].map((w, i) => (
              <div key={i} className="h-2.5 rounded" style={{ width: `${w}%`, background: 'rgb(var(--canvas-surface))' }} />
            ))}
          </div>
        ) : chunksQuery.isError ? (
          <p className="text-[11px]" style={{ color: 'rgb(var(--status-error))' }}>Failed to load preview</p>
        ) : contentPreview ? (
          <p className="text-[11px] leading-relaxed whitespace-pre-wrap break-words line-clamp-6" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
            {contentPreview}
          </p>
        ) : (
          <p className="text-[11px]" style={{ color: 'rgb(var(--canvas-fg-3))' }}>No preview available</p>
        )}
      </div>

      {/* Chunk list */}
      <div className="flex-1 px-5 py-4 overflow-y-auto">
        <p className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          Chunks ({chunks.length})
        </p>
        {chunksQuery.isLoading ? (
          <div className="space-y-2 animate-pulse">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-8 rounded" style={{ background: 'rgb(var(--canvas-surface))' }} />
            ))}
          </div>
        ) : chunksQuery.isError ? (
          <p className="text-[11px]" style={{ color: 'rgb(var(--status-error))' }}>Failed to load chunks</p>
        ) : chunks.length === 0 ? (
          <p className="text-[11px]" style={{ color: 'rgb(var(--canvas-fg-3))' }}>No chunks indexed</p>
        ) : (
          <div className="space-y-1">
            {chunks.map(chunk => (
              <div
                key={chunk.chunk_hash}
                className="px-2.5 py-2 rounded text-[11px]"
                style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-bg-2))` }}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <span
                    className="px-1.5 py-0.5 rounded text-[9px] font-medium uppercase"
                    style={{ background: getDomainColorWithAlpha('documents', '20'), color: docColor }}
                  >
                    {chunk.chunk_type}
                  </span>
                  <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>#{chunk.chunk_index}</span>
                </div>
                {chunk.context_header && (
                  <p className="truncate mt-0.5" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                    {chunk.context_header}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── DocumentsPage ─────────────────────────────────────────────────

export default function DocumentsPage(): ReactNode {
  const navigate = useNavigate();
  const {
    folder: selectedFolder = '',
    source_id: selectedSourceId,
    view = 'grid',
    sort = 'date',
  } = useSearch({ from: '/documents' });

  const [filterText, setFilterText] = useState('');
  const [showSortMenu, setShowSortMenu] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [adapterFilter, setAdapterFilter] = useState<string>('');

  const sourcesQuery = useSources({ domain: 'documents', limit: 1000 });
  const sources = sourcesQuery.data?.sources ?? [];

  const folderTree = useMemo(() => buildFolderTree(sources), [sources]);
  const rootFolders = useMemo(() => getSubfolders(folderTree, ''), [folderTree]);

  // Available adapters for the filter dropdown
  const availableAdapters = useMemo(() =>
    Array.from(new Set(sources.map(s => s.adapter_id))).sort(),
    [sources],
  );

  // Files in selected folder, with adapter and type filter applied
  const folderFiles = useMemo(() => {
    const direct = folderTree.get(selectedFolder) ?? [];
    return sortSources(direct, sort as SortKey);
  }, [folderTree, selectedFolder, sort]);

  const filteredFiles = useMemo(() => {
    let list = folderFiles;
    if (filterText.trim()) {
      const q = filterText.toLowerCase();
      list = list.filter(s => getFilename(s.origin_ref).toLowerCase().includes(q));
    }
    if (typeFilter.length > 0) {
      list = list.filter(s => typeFilter.includes(categorizeFile(s.origin_ref)));
    }
    if (adapterFilter) {
      list = list.filter(s => s.adapter_id === adapterFilter);
    }
    return list;
  }, [folderFiles, filterText, typeFilter, adapterFilter]);

  const selectedSource = useMemo(() => {
    if (!selectedSourceId) return null;
    const inFiltered = filteredFiles.some(s => s.source_id === selectedSourceId);
    if (!inFiltered) return null;
    return sources.find(s => s.source_id === selectedSourceId) ?? null;
  }, [sources, selectedSourceId, filteredFiles]);

  const totalChunks = sources.reduce((sum, s) => sum + s.chunk_count, 0);

  function selectFolder(path: string): void {
    void navigate({ to: '/documents', search: { folder: path, view, sort } });
  }

  function selectFile(sourceId: string): void {
    void navigate({ to: '/documents', search: { folder: selectedFolder, source_id: sourceId, view, sort } });
  }

  function setView(v: 'grid' | 'list'): void {
    void navigate({ to: '/documents', search: { folder: selectedFolder, source_id: selectedSourceId, view: v, sort } });
  }

  function setSort(s: SortKey): void {
    setShowSortMenu(false);
    void navigate({ to: '/documents', search: { folder: selectedFolder, source_id: selectedSourceId, view, sort: s } });
  }

  const breadcrumbSegments = selectedFolder ? selectedFolder.split('/') : [];
  const SORT_LABELS: Record<string, string> = { name: 'Name', date: 'Modified', size: 'Size', type: 'Type' };

  // ── Folder tree panel ──────────────────────────────────────────

  const folderTreePanel = (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-surface))' }}>
      <div className="px-3 pt-3 pb-1 shrink-0">
        <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          Folders
        </span>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {sourcesQuery.isLoading ? (
          <div className="px-3 py-2 space-y-2">
            {[60, 80, 50, 70, 90].map((w, i) => (
              <div key={i} className="h-3 rounded animate-pulse" style={{ width: `${w}%`, background: 'rgb(var(--canvas-bg-2))' }} />
            ))}
          </div>
        ) : sourcesQuery.isError ? (
          <div className="px-3 py-2 text-xs" style={{ color: 'rgb(var(--status-error))' }}>
            Failed to load folders
          </div>
        ) : rootFolders.length === 0 && folderTree.get('')?.length === 0 ? (
          <div className="px-3 py-2 text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            No documents found
          </div>
        ) : (
          <HierarchyTree>
            {(folderTree.get('') ?? []).length > 0 && (
              <HierarchyRow
                depth={0}
                domain="software"
                kind="taxonomy"
                label="~/"
                meta={String((folderTree.get('') ?? []).length)}
                selected={selectedFolder === ''}
                onSelect={() => selectFolder('')}
                showKind={false}
              />
            )}
            {rootFolders.map(folder => (
              <FolderTreeItem
                key={folder}
                name={folder}
                fullPath={folder}
                tree={folderTree}
                selectedFolder={selectedFolder}
                depth={0}
                onSelect={selectFolder}
              />
            ))}
          </HierarchyTree>
        )}
      </div>
    </div>
  );

  // ── Main grid panel ────────────────────────────────────────────

  const mainGridPanel = (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      {/* Topbar with breadcrumbs and controls */}
      <div
        className="flex items-center gap-3 shrink-0 px-4"
        style={{ height: 52, background: 'rgb(var(--canvas-surface))', borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          <button
            onClick={() => selectFolder('')}
            className="flex items-center gap-1 shrink-0 transition-colors hover:opacity-80"
          >
            <HomeIcon style={{ width: 12, height: 12, color: 'rgb(var(--canvas-fg-3))' }} />
            <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>~/</span>
          </button>
          {breadcrumbSegments.map((seg, i) => {
            const path = breadcrumbSegments.slice(0, i + 1).join('/');
            const isLast = i === breadcrumbSegments.length - 1;
            return (
              <span key={path} className="flex items-center gap-1.5 shrink-0">
                <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  <Icon name="chevronRight" size={12} />
                </span>
                <button
                  onClick={() => selectFolder(path)}
                  className="text-xs transition-colors hover:opacity-80"
                  style={{ color: isLast ? 'rgb(var(--canvas-fg-1))' : 'rgb(var(--canvas-fg-3))' }}
                >
                  {seg}
                </button>
              </span>
            );
          })}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 shrink-0">
          {/* View toggle */}
          <div
            className="flex items-center rounded"
            style={{ background: 'rgb(var(--canvas-bg-2))', border: `1px solid rgb(var(--canvas-border))`, height: 32 }}
          >
            <button
              onClick={() => setView('grid')}
              className="flex items-center justify-center rounded transition-colors"
              style={{
                width: 32, height: 28,
                background: view === 'grid' ? 'rgb(var(--canvas-surface))' : 'transparent',
                margin: 2,
              }}
              title="Grid view"
            >
              <Squares2X2Icon style={{ width: 14, height: 14, color: view === 'grid' ? docColor : 'rgb(var(--canvas-fg-3))' }} />
            </button>
            <button
              onClick={() => setView('list')}
              className="flex items-center justify-center rounded transition-colors"
              style={{
                width: 32, height: 28,
                background: view === 'list' ? 'rgb(var(--canvas-surface))' : 'transparent',
                margin: 2,
              }}
              title="List view"
            >
              <ListBulletIcon style={{ width: 14, height: 14, color: view === 'list' ? docColor : 'rgb(var(--canvas-fg-3))' }} />
            </button>
          </div>
        </div>
      </div>

      {/* Filter + sort bar */}
      <div
        className="flex items-center gap-3 px-4 py-2 shrink-0"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        <div
          className="flex items-center gap-2 px-2.5 py-1.5 rounded flex-1"
          style={{ background: 'rgb(var(--canvas-surface))', maxWidth: 260 }}
        >
          <span style={{ color: 'rgb(var(--canvas-fg-3))', flexShrink: 0 }}>
            <Icon name="search" size={12} />
          </span>
          <input
            type="text"
            value={filterText}
            onChange={e => setFilterText(e.target.value)}
            placeholder="Filter files…"
            className="bg-transparent text-xs outline-none flex-1"
            style={{ color: 'rgb(var(--canvas-fg-1))' }}
          />
        </div>

        <FilterDropdown
          mode="checkbox"
          value={typeFilter}
          onChange={setTypeFilter}
        >
          <FilterDropdown.Trigger
            label="Type"
            summary={typeFilter.length === 0 ? 'All' : `${typeFilter.length} types`}
          />
          <FilterDropdown.Panel>
            <FilterDropdown.Section title="File type">
              {(['pdf', 'text', 'code', 'image', 'spreadsheet', 'audio', 'video', 'archive', 'other'] satisfies FileCategory[]).map(cat => (
                <FilterDropdown.Checkbox key={cat} value={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)} />
              ))}
            </FilterDropdown.Section>
          </FilterDropdown.Panel>
        </FilterDropdown>

        <FilterDropdown
          mode="radio"
          value={adapterFilter ? [adapterFilter] : []}
          onChange={vals => setAdapterFilter(vals[0] ?? '')}
        >
          <FilterDropdown.Trigger
            label="Adapter"
            summary={adapterFilter ? adapterFilter.split(':')[0].replace(/_/g, ' ') : 'All'}
          />
          <FilterDropdown.Panel>
            <FilterDropdown.Section title="Source adapter">
              <FilterDropdown.Radio value="" label="All Adapters" />
              {availableAdapters.map(id => (
                <FilterDropdown.Radio key={id} value={id} label={id.split(':')[0].replace(/_/g, ' ')} />
              ))}
            </FilterDropdown.Section>
          </FilterDropdown.Panel>
        </FilterDropdown>

        <span className="text-xs flex-1 text-right" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          {filteredFiles.length} {filteredFiles.length === 1 ? 'file' : 'files'} · {totalChunks.toLocaleString()} indexed
        </span>

        {/* Sort dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowSortMenu(v => !v)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors"
            style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-2))', border: `1px solid rgb(var(--canvas-border))` }}
          >
            <ArrowsUpDownIcon style={{ width: 12, height: 12, color: 'rgb(var(--canvas-fg-3))' }} />
            {SORT_LABELS[sort]}
            <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              <Icon name="chevronDown" size={10} />
            </span>
          </button>
          {showSortMenu && (
            <div
              className="absolute right-0 top-8 z-10 rounded-lg py-1 min-w-[100px]"
              style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-border))`, boxShadow: '0 4px 16px rgba(0,0,0,0.5)' }}
            >
              {(['name', 'date', 'size', 'type'] satisfies SortKey[]).map(key => (
                <button
                  key={key}
                  onClick={() => setSort(key)}
                  className="w-full text-left px-3 py-1.5 text-xs transition-colors hover:bg-white/5"
                  style={{ color: sort === key ? docColor : 'rgb(var(--canvas-fg-2))' }}
                >
                  {SORT_LABELS[key]}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* File content */}
      <div className="flex-1 overflow-y-auto p-4">
        {sourcesQuery.isLoading ? (
          <AssetGrid columns={4}>
            {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
              <div
                key={i}
                className="animate-pulse rounded-lg"
                style={{ height: 130, background: 'rgb(var(--canvas-surface))' }}
              />
            ))}
          </AssetGrid>
        ) : sourcesQuery.isError ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 py-16">
            <p className="text-sm" style={{ color: 'rgb(var(--status-error))' }}>Failed to load documents</p>
          </div>
        ) : filteredFiles.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 py-16">
            <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              <Icon name="folder" size={32} />
            </span>
            <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              {filterText || typeFilter.length > 0 ? 'No files match your filters' : 'No files in this folder'}
            </p>
          </div>
        ) : view === 'grid' ? (
          <AssetGrid columns={4} gap={12}>
            {filteredFiles.map(source => {
              const filename = getFilename(source.origin_ref);
              const ext = getExtension(filename);
              const isSelected = source.source_id === selectedSourceId;
              return (
                <div
                  key={source.source_id}
                  onClick={() => selectFile(source.source_id)}
                  style={{ cursor: 'pointer' }}
                >
                  <AssetCard
                    thumb={{ kind: 'doc', ext: ext || 'file' }}
                    title={filename}
                    subtitle={formatDate(source.updated_at)}
                    meta={<span style={{ fontSize: 10, color: 'rgb(var(--canvas-fg-3))' }}>{source.chunk_count} chunks</span>}
                    badge={ext.toUpperCase() || 'FILE'}
                    selected={isSelected}
                  />
                </div>
              );
            })}
          </AssetGrid>
        ) : (
          <div className="flex flex-col">
            <div
              className="flex items-center gap-3 px-4 py-1.5 mb-1"
              style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
            >
              <span className="flex-1 text-[10px] font-semibold uppercase tracking-wide" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Name</span>
              <span className="text-[10px] font-semibold uppercase tracking-wide w-20 text-right shrink-0" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Modified</span>
              <span className="text-[10px] font-semibold uppercase tracking-wide w-16 text-right shrink-0" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Chunks</span>
            </div>
            {filteredFiles.map(source => (
              <FileRow
                key={source.source_id}
                source={source}
                isSelected={source.source_id === selectedSourceId}
                onClick={() => selectFile(source.source_id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Domains"
        title="Documents"
        subtitle="Ingested filesystem documents"
      />
      <div className="flex-1 min-h-0 overflow-hidden">
        <SplitPane
          direction="horizontal"
          initialSplitPercent={20}
          minSize={160}
          maxSize={380}
          first={folderTreePanel}
          second={
            selectedSource ? (
              <SplitPane
                direction="horizontal"
                initialSplitPercent={65}
                minSize={280}
                maxSize={600}
                first={mainGridPanel}
                second={
                  <div
                    className="h-full overflow-hidden"
                    style={{ background: 'rgb(var(--canvas-surface))' }}
                  >
                    <FileDetail source={selectedSource} />
                  </div>
                }
              />
            ) : (
              mainGridPanel
            )
          }
          style={{ height: '100%' }}
        />
      </div>
    </div>
  );
}
