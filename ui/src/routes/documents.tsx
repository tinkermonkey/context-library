import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  FolderIcon,
  FolderOpenIcon,
  MagnifyingGlassIcon,
  Squares2X2Icon,
  ListBulletIcon,
  DocumentTextIcon,
  DocumentIcon,
  PhotoIcon,
  CodeBracketIcon,
  ArchiveBoxIcon,
  TableCellsIcon,
  FilmIcon,
  MusicalNoteIcon,
  ChevronRightIcon,
  HomeIcon,
  ArrowsUpDownIcon,
  ChevronDownIcon,
} from '@heroicons/react/24/outline';
import { useSources } from '../hooks/useSources';
import { fetchSourceChunks } from '../api/client';
import { colors, getDomainColor } from '../lib/designTokens';
import type { SourceSummary, ChunkResponse } from '../types/api';
import { extractDocumentMetadata } from '../types/api';

const docColor = getDomainColor('documents'); // #22C55E

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

const CATEGORY_COLORS: Record<FileCategory, string> = {
  pdf: '#6366F1',
  text: '#22C55E',
  code: '#06B6D4',
  image: '#F59E0B',
  archive: '#F97316',
  spreadsheet: '#10B981',
  video: '#EC4899',
  audio: '#F43F5E',
  other: '#6B7280',
};

function FileTypeIcon({ category, size = 20 }: { category: FileCategory; size?: number }): ReactNode {
  const color = CATEGORY_COLORS[category];
  const cls = `shrink-0`;
  const style = { width: size, height: size, color };
  switch (category) {
    case 'pdf': return <DocumentTextIcon className={cls} style={style} />;
    case 'text': return <DocumentTextIcon className={cls} style={style} />;
    case 'code': return <CodeBracketIcon className={cls} style={style} />;
    case 'image': return <PhotoIcon className={cls} style={style} />;
    case 'archive': return <ArchiveBoxIcon className={cls} style={style} />;
    case 'spreadsheet': return <TableCellsIcon className={cls} style={style} />;
    case 'video': return <FilmIcon className={cls} style={style} />;
    case 'audio': return <MusicalNoteIcon className={cls} style={style} />;
    default: return <DocumentIcon className={cls} style={style} />;
  }
}

// ── Path utilities ────────────────────────────────────────────────

/**
 * Parse all source origin_refs to extract a normalized directory tree.
 * Returns a Map of folder path → list of sources in that folder.
 *
 * NOTE: origin_ref is assumed to always be Unix-style forward-slash paths,
 * as normalized by the FilesystemAdapter before storage. Windows-style paths
 * (backslash or drive letters) are not supported.
 */
function buildFolderTree(sources: SourceSummary[]): Map<string, SourceSummary[]> {
  const tree = new Map<string, SourceSummary[]>();
  // Root always exists
  tree.set('', []);

  for (const source of sources) {
    // Normalize leading slashes so absolute paths like /Users/foo/bar.pdf
    // produce segments ['Users', 'foo', 'bar.pdf'] rather than ['', 'Users', ...]
    const parts = source.origin_ref.replace(/^\/+/, '').split('/').filter(Boolean);
    if (parts.length === 0) continue;

    // Add source to its immediate parent folder
    const parentParts = parts.slice(0, -1);
    const parentPath = parentParts.join('/');
    if (!tree.has(parentPath)) tree.set(parentPath, []);
    tree.get(parentPath)!.push(source);

    // Ensure all ancestor folders exist in tree
    for (let i = 1; i < parentParts.length; i++) {
      const ancestorPath = parentParts.slice(0, i).join('/');
      if (!tree.has(ancestorPath)) tree.set(ancestorPath, []);
    }
  }

  return tree;
}

/**
 * Get immediate subdirectory names for a given folder path.
 */
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

/**
 * Count files recursively under a folder (including subdirectories).
 * The root folder ('') only counts files directly at the root level.
 */
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
      case 'size': {
        // file_size_bytes is in domain_metadata, use chunk_count as proxy if unavailable
        return b.chunk_count - a.chunk_count;
      }
      case 'type': {
        const extA = getExtension(getFilename(a.origin_ref));
        const extB = getExtension(getFilename(b.origin_ref));
        return extA.localeCompare(extB);
      }
      default: return 0;
    }
  });
}

// ── FolderTree ────────────────────────────────────────────────────

function FolderTreeNode({
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
  const isOpen = isSelected || isAncestor || subfolders.length === 0;

  return (
    <div>
      <button
        onClick={() => onSelect(fullPath)}
        className="w-full flex items-center gap-2 py-1 rounded transition-colors text-left"
        style={{
          paddingLeft: depth === 0 ? 12 : depth * 12 + 8,
          paddingRight: 12,
          height: 32,
          background: isSelected ? '#1A1F3C' : 'transparent',
        }}
      >
        {isSelected || isAncestor ? (
          <FolderOpenIcon
            style={{ width: 14, height: 14, color: isSelected ? '#A5B4FC' : '#6B7280', flexShrink: 0 }}
          />
        ) : (
          <FolderIcon
            style={{ width: 14, height: 14, color: '#6B7280', flexShrink: 0 }}
          />
        )}
        <span
          className="text-xs truncate flex-1 leading-none"
          style={{ color: isSelected ? '#FFFFFF' : '#9CA3AF' }}
        >
          {name}
        </span>
        {fileCount > 0 && (
          <span className="text-xs ml-auto shrink-0 tabular-nums" style={{ color: '#4B5563' }}>
            {fileCount}
          </span>
        )}
      </button>

      {isOpen && subfolders.map(sub => (
        <FolderTreeNode
          key={sub}
          name={sub}
          fullPath={fullPath ? `${fullPath}/${sub}` : sub}
          tree={tree}
          selectedFolder={selectedFolder}
          depth={depth + 1}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

// ── FileCard (grid view) ──────────────────────────────────────────

function FileCard({
  source,
  isSelected,
  onClick,
}: {
  source: SourceSummary;
  isSelected: boolean;
  onClick: () => void;
}): ReactNode {
  const filename = getFilename(source.origin_ref);
  const category = categorizeFile(source.origin_ref);
  const ext = getExtension(filename).toUpperCase() || 'FILE';

  return (
    <button
      onClick={onClick}
      className="flex flex-col gap-2.5 rounded-lg p-3.5 text-left transition-all"
      style={{
        width: 180,
        background: isSelected ? '#1A1F3C' : '#161616',
        border: `1px solid ${isSelected ? '#312E81' : '#1E1E1E'}`,
        flexShrink: 0,
      }}
    >
      {/* Icon */}
      <div
        className="flex items-center justify-center rounded-lg shrink-0"
        style={{ width: 40, height: 40, background: '#1C1A2E' }}
      >
        <FileTypeIcon category={category} size={20} />
      </div>

      {/* Filename */}
      <span
        className="text-xs font-medium leading-snug"
        style={{
          color: isSelected ? '#FFFFFF' : '#E5E7EB',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          width: '100%',
        }}
      >
        {filename}
      </span>

      {/* Meta */}
      <div className="flex flex-col gap-0.5">
        <span className="text-[10px]" style={{ color: isSelected ? '#818CF8' : '#6B7280' }}>
          {ext}
        </span>
        <span className="text-[10px]" style={{ color: isSelected ? '#A5B4FC' : '#4B5563' }}>
          {formatDate(source.updated_at)}
        </span>
      </div>
    </button>
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
  const category = categorizeFile(source.origin_ref);

  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-2 transition-colors text-left"
      style={{
        background: isSelected ? '#1A1F3C' : 'transparent',
        borderLeft: `2px solid ${isSelected ? '#6366F1' : 'transparent'}`,
      }}
    >
      <FileTypeIcon category={category} size={14} />
      <span
        className="flex-1 text-xs truncate"
        style={{ color: isSelected ? '#FFFFFF' : '#E5E7EB' }}
      >
        {filename}
      </span>
      <span className="text-[10px] shrink-0 w-20 text-right" style={{ color: colors.textDim }}>
        {formatDate(source.updated_at)}
      </span>
      <span className="text-[10px] shrink-0 w-16 text-right" style={{ color: colors.textDim }}>
        {source.chunk_count} {source.chunk_count === 1 ? 'chunk' : 'chunks'}
      </span>
    </button>
  );
}

// ── FileDetail (right panel) ──────────────────────────────────────

function FileDetail({ source }: { source: SourceSummary }): ReactNode {
  const filename = getFilename(source.origin_ref);
  const category = categorizeFile(source.origin_ref);
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

  // Extract file_size_bytes from first chunk's domain_metadata
  const docMeta = useMemo(() => {
    const first = chunks[0];
    if (!first?.domain_metadata) return null;
    try { return extractDocumentMetadata(first.domain_metadata); } catch { return null; }
  }, [chunks]);

  // Content preview: first 500 chars from first text chunk
  const contentPreview = useMemo(() => {
    const textChunk = chunks.find(c => c.chunk_type === 'text' || c.chunk_type === 'document');
    if (!textChunk) return chunks[0]?.content ?? null;
    return textChunk.content.slice(0, 500);
  }, [chunks]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 shrink-0" style={{ borderBottom: `1px solid ${colors.border}` }}>
        <div
          className="flex items-center justify-center rounded-xl mb-3"
          style={{ width: 48, height: 48, background: '#1C1A2E' }}
        >
          <FileTypeIcon category={category} size={24} />
        </div>
        <h2 className="text-sm font-semibold leading-snug mb-1" style={{ color: colors.textPrimary }}>
          {filename}
        </h2>
        <p className="text-[10px] break-all" style={{ color: colors.textDim }}>
          {source.origin_ref}
        </p>
      </div>

      {/* Metadata */}
      <div className="px-5 py-4 shrink-0 space-y-3" style={{ borderBottom: `1px solid ${colors.border}` }}>
        <p className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: colors.textDim }}>
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
      <div className="px-5 py-4 shrink-0" style={{ borderBottom: `1px solid ${colors.border}` }}>
        <p className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: colors.textDim }}>
          Preview
        </p>
        {chunksQuery.isLoading ? (
          <div className="space-y-1.5 animate-pulse">
            {[80, 65, 90, 55, 70].map((w, i) => (
              <div key={i} className="h-2.5 rounded" style={{ width: `${w}%`, background: colors.bgElevated }} />
            ))}
          </div>
        ) : chunksQuery.isError ? (
          <p className="text-[11px]" style={{ color: colors.statusRed }}>Failed to load preview</p>
        ) : contentPreview ? (
          <p className="text-[11px] leading-relaxed whitespace-pre-wrap break-words line-clamp-6" style={{ color: colors.textMuted }}>
            {contentPreview}
          </p>
        ) : (
          <p className="text-[11px]" style={{ color: colors.textDim }}>No preview available</p>
        )}
      </div>

      {/* Chunk list */}
      <div className="flex-1 px-5 py-4 overflow-y-auto">
        <p className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: colors.textDim }}>
          Chunks ({chunks.length})
        </p>
        {chunksQuery.isLoading ? (
          <div className="space-y-2 animate-pulse">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-8 rounded" style={{ background: colors.bgElevated }} />
            ))}
          </div>
        ) : chunksQuery.isError ? (
          <p className="text-[11px]" style={{ color: colors.statusRed }}>Failed to load chunks</p>
        ) : chunks.length === 0 ? (
          <p className="text-[11px]" style={{ color: colors.textDim }}>No chunks indexed</p>
        ) : (
          <div className="space-y-1">
            {chunks.map(chunk => (
              <div
                key={chunk.chunk_hash}
                className="px-2.5 py-2 rounded text-[11px]"
                style={{ background: colors.bgElevated, border: `1px solid ${colors.borderSubtle}` }}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <span
                    className="px-1.5 py-0.5 rounded text-[9px] font-medium uppercase"
                    style={{ background: `${docColor}20`, color: docColor }}
                  >
                    {chunk.chunk_type}
                  </span>
                  <span style={{ color: colors.textDim }}>#{chunk.chunk_index}</span>
                </div>
                {chunk.context_header && (
                  <p className="truncate mt-0.5" style={{ color: colors.textDim }}>
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

function MetaRow({ label, value }: { label: string; value: string }): ReactNode {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-[10px] w-16 shrink-0" style={{ color: colors.textDim }}>{label}</span>
      <span className="text-[11px] truncate" style={{ color: colors.textMuted }}>{value}</span>
    </div>
  );
}

// ── EmptyState ────────────────────────────────────────────────────

function EmptyDetail(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 48, height: 48, background: `${docColor}20` }}
      >
        <FolderIcon style={{ width: 24, height: 24, color: docColor }} />
      </div>
      <p className="text-sm" style={{ color: colors.textDim }}>
        Select a file to view details
      </p>
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

  // 1000 is an intentional high cap — document libraries are expected to stay well
  // under this. If sourcesQuery.data?.total > 1000, the grid will silently truncate;
  // add pagination here if real-world usage exceeds this.
  const sourcesQuery = useSources({ domain: 'documents', limit: 1000 });
  const sources = sourcesQuery.data?.sources ?? [];

  const folderTree = useMemo(() => buildFolderTree(sources), [sources]);

  // Top-level folders (for the left sidebar)
  const rootFolders = useMemo(() => getSubfolders(folderTree, ''), [folderTree]);

  // Files in selected folder
  const folderFiles = useMemo(() => {
    const direct = folderTree.get(selectedFolder) ?? [];
    return sortSources(direct, sort as SortKey);
  }, [folderTree, selectedFolder, sort]);

  // Apply search filter
  const filteredFiles = useMemo(() => {
    if (!filterText.trim()) return folderFiles;
    const q = filterText.toLowerCase();
    return folderFiles.filter(s => getFilename(s.origin_ref).toLowerCase().includes(q));
  }, [folderFiles, filterText]);

  // If the selected file is no longer visible after filtering, treat it as deselected
  // so the right panel doesn't show stale content the user can't see in the grid.
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

  // Build breadcrumb segments from selectedFolder
  const breadcrumbSegments = selectedFolder ? selectedFolder.split('/') : [];

  const SORT_LABELS: Record<string, string> = { name: 'Name', date: 'Modified', size: 'Size', type: 'Type' };

  return (
    <div className="flex h-full overflow-hidden" style={{ background: colors.bgBase }}>

      {/* ── Left panel: folder tree ── */}
      <div
        className="shrink-0 flex flex-col overflow-hidden"
        style={{ width: 220, borderRight: `1px solid ${colors.border}`, background: '#0D0D0D' }}
      >
        {/* Label */}
        <div className="px-3 pt-3 pb-1 shrink-0">
          <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: '#4B5563' }}>
            Folders
          </span>
        </div>

        {/* Tree */}
        <div className="flex-1 overflow-y-auto py-1">
          {sourcesQuery.isLoading ? (
            <div className="px-3 py-2 space-y-2">
              {[60, 80, 50, 70, 90].map((w, i) => (
                <div key={i} className="h-3 rounded animate-pulse" style={{ width: `${w}%`, background: colors.bgElevated }} />
              ))}
            </div>
          ) : sourcesQuery.isError ? (
            <div className="px-3 py-2 text-xs" style={{ color: colors.statusRed }}>
              Failed to load folders
            </div>
          ) : rootFolders.length === 0 && folderTree.get('')?.length === 0 ? (
            <div className="px-3 py-2 text-xs" style={{ color: colors.textDim }}>
              No documents found
            </div>
          ) : (
            <>
              {/* Root files (if any) */}
              {(folderTree.get('') ?? []).length > 0 && (
                <button
                  onClick={() => selectFolder('')}
                  className="w-full flex items-center gap-2 py-1 rounded transition-colors"
                  style={{
                    paddingLeft: 12, paddingRight: 12, height: 32,
                    background: selectedFolder === '' ? '#1A1F3C' : 'transparent',
                  }}
                >
                  <HomeIcon style={{ width: 14, height: 14, color: selectedFolder === '' ? '#A5B4FC' : '#6B7280', flexShrink: 0 }} />
                  <span className="text-xs" style={{ color: selectedFolder === '' ? '#FFFFFF' : '#9CA3AF' }}>~/</span>
                  <span className="text-xs ml-auto tabular-nums" style={{ color: '#4B5563' }}>
                    {(folderTree.get('') ?? []).length}
                  </span>
                </button>
              )}
              {rootFolders.map(folder => (
                <FolderTreeNode
                  key={folder}
                  name={folder}
                  fullPath={folder}
                  tree={folderTree}
                  selectedFolder={selectedFolder}
                  depth={0}
                  onSelect={selectFolder}
                />
              ))}
            </>
          )}
        </div>
      </div>

      {/* ── Main area: topbar + file grid ── */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">

        {/* Topbar */}
        <div
          className="flex items-center gap-3 shrink-0 px-5"
          style={{ height: 52, background: '#111111', borderBottom: `1px solid #1A1A1A` }}
        >
          {/* Title */}
          <span className="text-base font-semibold shrink-0" style={{ color: '#FFFFFF' }}>
            Documents
          </span>

          {/* Breadcrumb */}
          <div className="flex items-center gap-1.5 flex-1 min-w-0">
            <button
              onClick={() => selectFolder('')}
              className="flex items-center gap-1 shrink-0 transition-colors hover:opacity-80"
            >
              <HomeIcon style={{ width: 12, height: 12, color: '#6B7280' }} />
              <span className="text-xs" style={{ color: '#6B7280' }}>~/</span>
            </button>
            {breadcrumbSegments.map((seg, i) => {
              const path = breadcrumbSegments.slice(0, i + 1).join('/');
              const isLast = i === breadcrumbSegments.length - 1;
              return (
                <span key={path} className="flex items-center gap-1.5 shrink-0">
                  <ChevronRightIcon style={{ width: 12, height: 12, color: '#4B5563' }} />
                  <button
                    onClick={() => selectFolder(path)}
                    className="text-xs transition-colors hover:opacity-80"
                    style={{ color: isLast ? '#FFFFFF' : '#9CA3AF' }}
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
              style={{ background: '#1A1A1A', border: '1px solid #2D2D2D', height: 32 }}
            >
              <button
                onClick={() => setView('grid')}
                className="flex items-center justify-center rounded transition-colors"
                style={{
                  width: 32, height: 28,
                  background: view === 'grid' ? '#312E81' : 'transparent',
                  margin: 2,
                }}
                title="Grid view"
              >
                <Squares2X2Icon style={{ width: 14, height: 14, color: view === 'grid' ? '#A5B4FC' : '#6B7280' }} />
              </button>
              <button
                onClick={() => setView('list')}
                className="flex items-center justify-center rounded transition-colors"
                style={{
                  width: 32, height: 28,
                  background: view === 'list' ? '#312E81' : 'transparent',
                  margin: 2,
                }}
                title="List view"
              >
                <ListBulletIcon style={{ width: 14, height: 14, color: view === 'list' ? '#A5B4FC' : '#6B7280' }} />
              </button>
            </div>
          </div>
        </div>

        {/* Stats + sort bar */}
        <div
          className="flex items-center gap-3 px-5 py-2 shrink-0"
          style={{ borderBottom: `1px solid ${colors.border}` }}
        >
          {/* Search */}
          <div
            className="flex items-center gap-2 px-2.5 py-1.5 rounded flex-1"
            style={{ background: colors.bgElevated, maxWidth: 260 }}
          >
            <MagnifyingGlassIcon style={{ width: 12, height: 12, color: colors.textDim, flexShrink: 0 }} />
            <input
              type="text"
              value={filterText}
              onChange={e => setFilterText(e.target.value)}
              placeholder="Filter files…"
              className="bg-transparent text-xs outline-none flex-1"
              style={{ color: colors.textPrimary }}
            />
          </div>

          {/* Count */}
          <span className="text-xs flex-1" style={{ color: '#6B7280' }}>
            {filteredFiles.length} {filteredFiles.length === 1 ? 'file' : 'files'} · {totalChunks.toLocaleString()} indexed
          </span>

          {/* Sort dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowSortMenu(v => !v)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors"
              style={{ background: '#1A1A1A', color: '#9CA3AF', border: '1px solid transparent' }}
            >
              <ArrowsUpDownIcon style={{ width: 12, height: 12, color: '#6B7280' }} />
              {SORT_LABELS[sort]}
              <ChevronDownIcon style={{ width: 10, height: 10, color: '#6B7280' }} />
            </button>
            {showSortMenu && (
              <div
                className="absolute right-0 top-8 z-10 rounded-lg py-1 min-w-[100px]"
                style={{ background: '#1A1A1A', border: `1px solid ${colors.border}`, boxShadow: '0 4px 16px #00000080' }}
              >
                {(['name', 'date', 'size', 'type'] satisfies SortKey[]).map(key => (
                  <button
                    key={key}
                    onClick={() => setSort(key)}
                    className="w-full text-left px-3 py-1.5 text-xs transition-colors hover:bg-[#252525]"
                    style={{ color: sort === key ? '#A5B4FC' : '#9CA3AF' }}
                  >
                    {SORT_LABELS[key]}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* File grid / list */}
        <div className="flex-1 overflow-y-auto p-5">
          {sourcesQuery.isLoading ? (
            <div className="flex flex-wrap gap-3">
              {[1, 2, 3, 4, 5, 6].map(i => (
                <div
                  key={i}
                  className="animate-pulse rounded-lg"
                  style={{ width: 180, height: 110, background: colors.bgElevated }}
                />
              ))}
            </div>
          ) : sourcesQuery.isError ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 py-16">
              <p className="text-sm" style={{ color: colors.statusRed }}>Failed to load documents</p>
              <button
                onClick={() => sourcesQuery.refetch()}
                className="text-xs px-3 py-1.5 rounded transition-colors"
                style={{ background: colors.bgElevated, color: colors.textMuted }}
              >
                Retry
              </button>
            </div>
          ) : filteredFiles.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 py-16">
              <FolderOpenIcon style={{ width: 32, height: 32, color: colors.textDim }} />
              <p className="text-sm" style={{ color: colors.textDim }}>
                {filterText ? 'No files match your filter' : 'No files in this folder'}
              </p>
            </div>
          ) : view === 'grid' ? (
            <div className="flex flex-wrap gap-3 content-start">
              {filteredFiles.map(source => (
                <FileCard
                  key={source.source_id}
                  source={source}
                  isSelected={source.source_id === selectedSourceId}
                  onClick={() => selectFile(source.source_id)}
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-col">
              {/* List header */}
              <div
                className="flex items-center gap-3 px-4 py-1.5 mb-1"
                style={{ borderBottom: `1px solid ${colors.border}` }}
              >
                <span className="flex-1 text-[10px] font-semibold uppercase tracking-wide" style={{ color: colors.textDim }}>Name</span>
                <span className="text-[10px] font-semibold uppercase tracking-wide w-20 text-right shrink-0" style={{ color: colors.textDim }}>Modified</span>
                <span className="text-[10px] font-semibold uppercase tracking-wide w-16 text-right shrink-0" style={{ color: colors.textDim }}>Chunks</span>
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

      {/* ── Right panel: file detail ── */}
      {selectedSource && (
        <div
          className="shrink-0 flex flex-col overflow-hidden"
          style={{ width: 360, borderLeft: `1px solid ${colors.border}`, background: colors.bgSurface }}
        >
          <FileDetail source={selectedSource} />
        </div>
      )}
    </div>
  );
}
