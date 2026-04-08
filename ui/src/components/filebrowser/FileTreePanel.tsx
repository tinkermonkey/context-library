import { useState, useEffect, type ReactNode } from 'react';
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
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());

  // Fetch all document sources
  const { data: sourcesData, isLoading, isError } = useSources({
    domain: 'documents',
  });

  // Build file tree from sources
  const sources = sourcesData?.sources ?? [];
  const fileTree = buildFileTree(sources);

  // When selectedSourceId changes, expand its ancestors
  useEffect(() => {
    if (selectedSourceId) {
      const newExpanded = new Set(expandedFolders);
      // Extract path to selected file and expand all ancestor folders
      const parts = selectedSourceId.split('/');
      let currentPath = '';
      for (let i = 0; i < parts.length - 1; i++) {
        currentPath += (currentPath ? '/' : '') + parts[i];
        newExpanded.add(currentPath);
      }
      setExpandedFolders(newExpanded);
    }
  }, [selectedSourceId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner color="info" size="md" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded">
        <p className="text-red-900 font-semibold text-sm">Failed to load file tree</p>
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
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      newExpanded.add(path);
    }
    setExpandedFolders(newExpanded);
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
    <div className="h-full overflow-y-auto border-r border-gray-200 bg-white">
      {fileTree.map((node) => renderNode(node))}
    </div>
  );
}
