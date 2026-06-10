import { useState, type ReactNode } from 'react';
import { Icon } from '@tinkermonkey/heimdall-ui';

export interface TreeNode {
  id: string;
  label: string;
  type: 'folder' | 'file';
  children?: TreeNode[];
  /** Optional badge text displayed at row end (e.g., version numbers) */
  badge?: string;
  /** Arbitrary caller data passed through to onSelect */
  data?: unknown;
}

export interface HierarchyTreeProps {
  nodes: TreeNode[];
  selectedId?: string | null;
  /**
   * Controlled expansion state. When provided, the component uses this set to
   * determine which folders are open. Combine with onExpandToggle for full control.
   * When omitted, expansion state is managed internally.
   */
  expandedIds?: Set<string>;
  /**
   * Called when a folder row is clicked. In controlled mode, update expandedIds
   * in response. In uncontrolled mode, this is also called for side-effects.
   */
  onExpandToggle?: (id: string) => void;
  onSelect?: (node: TreeNode) => void;
  className?: string;
}

export function HierarchyTree({
  nodes,
  selectedId,
  expandedIds: controlledExpanded,
  onExpandToggle,
  onSelect,
  className,
}: HierarchyTreeProps): ReactNode {
  const [internalExpanded, setInternalExpanded] = useState<Set<string>>(new Set());

  const isControlled = controlledExpanded !== undefined;
  const expandedIds = isControlled ? controlledExpanded : internalExpanded;

  const handleFolderClick = (id: string) => {
    onExpandToggle?.(id);
    if (!isControlled) {
      setInternalExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
        return next;
      });
    }
  };

  const renderNode = (node: TreeNode, depth: number = 0): ReactNode => {
    const isFolder = node.type === 'folder';
    const isOpen = isFolder && expandedIds.has(node.id);
    const isSelected = selectedId === node.id;

    return (
      <div key={node.id}>
        <div
          className="flex items-center gap-1 text-sm cursor-pointer rounded"
          style={{
            paddingLeft: `${depth * 12 + 8}px`,
            paddingRight: 8,
            paddingTop: 4,
            paddingBottom: 4,
            background: isSelected ? `rgb(var(--accent-primary) / 0.15)` : 'transparent',
            borderLeft: isSelected
              ? `2px solid rgb(var(--accent-primary))`
              : '2px solid transparent',
          }}
          onMouseEnter={(e) => {
            if (!isSelected)
              e.currentTarget.style.background = `rgb(var(--canvas-fg-1) / 0.08)`;
          }}
          onMouseLeave={(e) => {
            if (!isSelected) e.currentTarget.style.background = 'transparent';
          }}
          onClick={() => {
            if (isFolder) {
              handleFolderClick(node.id);
            } else {
              onSelect?.(node);
            }
          }}
        >
          {isFolder ? (
            <span className="flex-shrink-0" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
              <Icon name={isOpen ? 'chevronDown' : 'chevronRight'} size={14} />
            </span>
          ) : (
            <span className="flex-shrink-0" style={{ width: 14 }} />
          )}
          <span
            className="flex-shrink-0"
            style={{
              color: isFolder
                ? `rgb(var(--domain-documents, var(--canvas-fg-2)))`
                : 'rgb(var(--accent-primary))',
            }}
          >
            <Icon name={isFolder ? 'folder' : 'file'} size={14} />
          </span>
          <span
            className="flex-1 truncate"
            style={{ color: 'rgb(var(--canvas-fg-1))', marginLeft: 4 }}
          >
            {node.label}
          </span>
          {node.badge && (
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: 'rgb(var(--canvas-fg-3))',
                flexShrink: 0,
                marginLeft: 4,
              }}
            >
              {node.badge}
            </span>
          )}
        </div>
        {isFolder && isOpen && node.children && (
          <div>
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return <div className={className}>{nodes.map((n) => renderNode(n))}</div>;
}
