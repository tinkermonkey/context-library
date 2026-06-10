import { useState, useMemo, type ReactNode } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Icon } from '@tinkermonkey/heimdall-ui';
import { useSources } from '../../hooks/useSources';
import { buildFileTree, type FileTreeNode, type FileNode } from '../../utils/fileTree';
import { HierarchyTree, type TreeNode } from '../HierarchyTree';
import type { FileBrowserPageSearch } from '../../router';

interface FileTreePanelProps {
  /** The selected source ID from URL, or null if no selection */
  selectedSourceId: string | null;
  /** Optional source ID prefix for subtree loading */
  sourceIdPrefix?: string;
}

const FILE_TREE_LIMIT = 5000;

function toTreeNodes(nodes: FileTreeNode[]): TreeNode[] {
  return nodes.map((node) => {
    if (node.type === 'folder') {
      return {
        id: node.path,
        label: node.name,
        type: 'folder',
        children: toTreeNodes(node.children),
      };
    }
    return {
      id: node.path,
      label: node.name,
      type: 'file',
      data: node.source,
    };
  });
}

export function FileTreePanel({ selectedSourceId, sourceIdPrefix }: FileTreePanelProps): ReactNode {
  const navigate = useNavigate({ from: '/browser/files' });
  const [manuallyExpandedFolders, setManuallyExpandedFolders] = useState<Set<string>>(
    new Set()
  );
  const [manuallyClosedFolders, setManuallyClosedFolders] = useState<Set<string>>(new Set());

  const { data: sourcesData, isLoading, isError, error } = useSources({
    domain: 'documents',
    source_id_prefix: sourceIdPrefix,
    limit: FILE_TREE_LIMIT,
  });

  const allSources = useMemo(() => sourcesData?.sources ?? [], [sourcesData?.sources]);
  // Filter to filesystem-based adapters only
  const sources = useMemo(
    () => allSources.filter((source) => source.adapter_id.startsWith('filesystem')),
    [allSources]
  );

  const fileTree = useMemo(() => buildFileTree(sources), [sources]);
  const treeNodes = useMemo(() => toTreeNodes(fileTree), [fileTree]);

  // Compute ancestor folder paths for the selected file so they auto-expand
  const ancestorIds = useMemo((): string[] => {
    if (!selectedSourceId) return [];
    const match = sources.find((s) => s.source_id === selectedSourceId);
    if (!match) return [];

    const adapterId = match.adapter_id;
    const parts = selectedSourceId.split('/').filter(Boolean);
    let currentPath = adapterId;
    const paths: string[] = [adapterId];
    for (let i = 0; i < parts.length - 1; i++) {
      currentPath += '/' + parts[i];
      paths.push(currentPath);
    }
    return paths;
  }, [selectedSourceId, sources]);

  // expandedIds = manually opened + ancestors (minus anything explicitly closed by user)
  const expandedIds = useMemo((): Set<string> => {
    const ids = new Set([...manuallyExpandedFolders]);
    for (const id of ancestorIds) {
      if (!manuallyClosedFolders.has(id)) ids.add(id);
    }
    return ids;
  }, [manuallyExpandedFolders, ancestorIds, manuallyClosedFolders]);

  const handleExpandToggle = (id: string) => {
    if (expandedIds.has(id)) {
      setManuallyExpandedFolders((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      // Track explicit close so ancestor auto-expand doesn't reopen it
      if (ancestorIds.includes(id)) {
        setManuallyClosedFolders((prev) => new Set([...prev, id]));
      }
    } else {
      setManuallyExpandedFolders((prev) => new Set([...prev, id]));
      setManuallyClosedFolders((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  // Map the selected source_id to the corresponding tree node path
  const selectedNodeId = useMemo((): string | null => {
    if (!selectedSourceId) return null;
    const match = sources.find((s) => s.source_id === selectedSourceId);
    if (!match) return null;
    const parts = selectedSourceId.split('/').filter(Boolean);
    let path = match.adapter_id;
    for (const part of parts) path += '/' + part;
    return path;
  }, [selectedSourceId, sources]);

  const handleSelect = (node: TreeNode) => {
    const source = node.data as FileNode['source'] | undefined;
    if (source?.source_id) {
      navigate({
        search: (prev: FileBrowserPageSearch) => ({
          ...prev,
          file: source.source_id,
        }),
      });
    }
  };

  const isTruncated =
    allSources.length > 0 &&
    allSources.length === (sourcesData?.limit ?? FILE_TREE_LIMIT) &&
    (sourcesData?.total ?? 0) > ((sourcesData?.offset ?? 0) + allSources.length);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Icon name="spinner" size={24} />
      </div>
    );
  }

  if (isError) {
    const errorMessage = error instanceof Error ? error.message : 'Failed to load file tree';
    return (
      <div
        className="p-4 rounded"
        style={{
          background: `rgb(var(--status-error) / 0.13)`,
          border: `1px solid rgb(var(--status-error) / 0.3)`,
        }}
      >
        <p className="font-semibold text-sm" style={{ color: 'rgb(var(--status-error))' }}>
          Error loading files
        </p>
        <p className="text-sm mt-2" style={{ color: 'rgb(var(--status-error) / 0.9)' }}>
          {errorMessage}
        </p>
      </div>
    );
  }

  if (sources.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          No files available
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {isTruncated && (
        <div
          className="p-3"
          style={{
            borderBottom: `1px solid rgb(var(--status-amber) / 0.3)`,
            background: `rgb(var(--status-amber) / 0.13)`,
          }}
        >
          <p className="text-xs" style={{ color: 'rgb(var(--status-amber))' }}>
            Showing {sources.length} filesystem files. More are available.
          </p>
        </div>
      )}
      <div className="flex-1 overflow-y-auto py-1">
        <HierarchyTree
          nodes={treeNodes}
          selectedId={selectedNodeId}
          expandedIds={expandedIds}
          onExpandToggle={handleExpandToggle}
          onSelect={handleSelect}
        />
      </div>
    </div>
  );
}
