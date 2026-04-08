import { useState, type ReactNode } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Spinner } from 'flowbite-react';
import { ChevronRightIcon, ChevronDownIcon, FolderIcon, DocumentIcon } from '@heroicons/react/24/outline';
import { useSources } from '../../hooks/useSources';
import { buildFileTree, type FileTreeNode } from '../../utils/fileTree';
import type { FileBrowserPageSearch } from '../../router';

interface FileTreePanelProps {
  /** The selected source ID from URL, or null if no selection */
  selectedSourceId: string | null;
}

/**
 * Left panel component that displays a hierarchical file tree.
 * Fetches all document sources, builds a tree structure, and allows navigation.
 * Updates the URL when a file is selected, supports expanding/collapsing folders,
 * and highlights the selected file.
 *
 * @example
 * <FileTreePanel selectedSourceId="filesystem:///path/to/file.txt" />
 */
export function FileTreePanel({ selectedSourceId }: FileTreePanelProps): ReactNode {
  const navigate = useNavigate({ from: '/browser/files' });
  const [manuallyExpandedFolders, setManuallyExpandedFolders] = useState<Set<string>>(new Set());

  // Fetch document sources with generous limit (5000) to ensure we capture all filesystem files
  // Filter to filesystem-based adapters client-side below to exclude non-filesystem sources
  // (music, YouTube, etc. from document-domain adapters)
  // TODO: Could optimize with source_id_prefix per-adapter for very large collections, but
  // currently fetching all documents and filtering is simpler given we need all adapters
  const { data: sourcesData, isLoading, isError, error } = useSources({
    domain: 'documents',
    limit: 5000,
  });

  // Filter to only filesystem-based adapters
  const allSources = sourcesData?.sources ?? [];
  const sources = allSources.filter((source) => {
    // Accept adapters with adapter_type starting with "Filesystem" (FilesystemAdapter,
    // FilesystemHelperAdapter, RichFilesystemAdapter, etc.)
    return source.adapter_type.startsWith('Filesystem');
  });

  // Build file tree from sources
  const fileTree = buildFileTree(sources);

  // Compute ancestor paths of selected file for auto-expansion
  const getSelectedFileAncestors = (): string[] => {
    if (!selectedSourceId) return [];

    // Find the matching source to determine its adapter_id
    const matchingSource = sources.find((s) => s.source_id === selectedSourceId);
    if (!matchingSource) return [];

    const adapterId = matchingSource.adapter_id;

    // Build paths with adapter_id prefix, matching tree node structure
    // The source_id is a relative path like "projects/alpha/file.md"
    // We need to build ancestor paths like "adapter_id/projects", "adapter_id/projects/alpha"
    const parts = selectedSourceId.split('/').filter(Boolean);
    let currentPath = adapterId;
    const ancestorPaths: string[] = [adapterId]; // Include root adapter node

    for (let i = 0; i < parts.length - 1; i++) {
      currentPath += '/' + parts[i];
      ancestorPaths.push(currentPath);
    }

    return ancestorPaths;
  };

  // Combine manually expanded folders with auto-expanded ancestors
  const expandedFolders = new Set([...manuallyExpandedFolders, ...getSelectedFileAncestors()]);

  // Check if API results are truncated by examining whether we hit the limit
  // If allSources.length equals the limit and total is higher, we got a full page with more available
  // Note: sourcesData.total includes ALL document sources (music, YouTube, etc.), not just filesystem ones,
  // so we must check against the limit/length, not against sourcesData.total directly
  const isTruncated =
    allSources.length > 0 &&
    allSources.length === (sourcesData?.limit ?? 0) &&
    (sourcesData?.total ?? 0) > ((sourcesData?.offset ?? 0) + allSources.length);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner color="info" size="md" />
      </div>
    );
  }

  if (isError) {
    const errorMessage = error instanceof Error ? error.message : 'Failed to load file tree';
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded">
        <p className="text-red-900 font-semibold text-sm">Error loading files</p>
        <p className="text-red-800 text-sm mt-2">{errorMessage}</p>
      </div>
    );
  }

  if (sources.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <p className="text-sm">No files available</p>
        </div>
      </div>
    );
  }

  const toggleFolder = (path: string) => {
    const newExpanded = new Set(manuallyExpandedFolders);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      newExpanded.add(path);
    }
    setManuallyExpandedFolders(newExpanded);
  };

  const handleFileClick = (node: FileTreeNode) => {
    if (node.source) {
      // Navigate and update URL with selected file
      navigate({
        search: (prev: FileBrowserPageSearch) => ({
          ...prev,
          file: node.source!.source_id,
        }),
      });
    }
  };

  const renderNode = (node: FileTreeNode, level: number = 0): ReactNode => {
    const isFolder = node.type === 'folder';
    const isExpanded = expandedFolders.has(node.path);
    const isSelected = node.type === 'file' && selectedSourceId === node.source?.source_id;

    return (
      <div key={node.path}>
        <div
          className={`flex items-center gap-1 px-2 py-1 text-sm cursor-pointer hover:bg-gray-100 rounded ${
            isSelected ? 'bg-blue-50 border-l-2 border-blue-500' : ''
          }`}
          style={{ paddingLeft: `${level * 12 + 8}px` }}
          onClick={() => {
            if (isFolder) {
              toggleFolder(node.path);
            } else {
              handleFileClick(node);
            }
          }}
        >
          {isFolder && (
            <span className="flex-shrink-0">
              {isExpanded ? (
                <ChevronDownIcon className="w-4 h-4 text-gray-600" />
              ) : (
                <ChevronRightIcon className="w-4 h-4 text-gray-600" />
              )}
            </span>
          )}
          {isFolder && <FolderIcon className="w-4 h-4 text-yellow-600 flex-shrink-0" />}
          {node.type === 'file' && <DocumentIcon className="w-4 h-4 text-blue-600 flex-shrink-0" />}
          <span className="truncate text-gray-900">{node.name}</span>
        </div>

        {isFolder && isExpanded && node.children && (
          <div>
            {node.children.map((child) => renderNode(child, level + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col">
      {isTruncated && (
        <div className="p-3 bg-yellow-50 border-b border-yellow-200">
          <p className="text-yellow-800 text-xs">
            Showing {sources.length} filesystem files (limit: {sourcesData?.limit ?? 5000}). More are available.
          </p>
        </div>
      )}
      <div className="flex-1 overflow-y-auto">
        {fileTree.map((node) => renderNode(node))}
      </div>
    </div>
  );
}
