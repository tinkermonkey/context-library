/**
 * File tree building utilities for the file browser.
 * Converts flat source lists into hierarchical folder/file structures.
 */

import type { SourceSummary } from '../types/api';

/**
 * Represents a node in the file tree structure.
 * Can be either a folder (with children) or a file (leaf node).
 */
export interface FileTreeNode {
  name: string;
  path: string;
  type: 'folder' | 'file';
  children?: FileTreeNode[];
  source?: SourceSummary;
}

/**
 * Builds a hierarchical file tree from a flat list of sources.
 *
 * Groups sources by adapter_id at the root level, then splits each source_id
 * on '/' to create intermediate folder nodes. Intermediate folders are synthesized
 * if they don't directly contain files.
 *
 * @example
 * buildFileTree([
 *   { source_id: 'projects/alpha/design.md', adapter_id: 'filesystem_helper:a' }
 * ]) => [
 *   {
 *     name: 'filesystem_helper:a',
 *     path: 'filesystem_helper:a',
 *     type: 'folder',
 *     children: [
 *       {
 *         name: 'projects',
 *         path: 'filesystem_helper:a/projects',
 *         type: 'folder',
 *         children: [
 *           {
 *             name: 'alpha',
 *             path: 'filesystem_helper:a/projects/alpha',
 *             type: 'folder',
 *             children: [
 *               {
 *                 name: 'design.md',
 *                 path: 'filesystem_helper:a/projects/alpha/design.md',
 *                 type: 'file',
 *                 source: { ... }
 *               }
 *             ]
 *           }
 *         ]
 *       }
 *     ]
 *   }
 * ]
 */
export function buildFileTree(sources: SourceSummary[]): FileTreeNode[] {
  // Group sources by adapter_id
  const adapterMap = new Map<string, SourceSummary[]>();

  for (const source of sources) {
    if (!adapterMap.has(source.adapter_id)) {
      adapterMap.set(source.adapter_id, []);
    }
    adapterMap.get(source.adapter_id)!.push(source);
  }

  // Build tree for each adapter
  const rootNodes: FileTreeNode[] = [];

  for (const [adapterId, adapterSources] of adapterMap) {
    const adapterRootNode: FileTreeNode = {
      name: adapterId,
      path: adapterId,
      type: 'folder',
      children: [],
    };

    // Build subtree for each source in this adapter
    for (const source of adapterSources) {
      insertSourceIntoTree(adapterRootNode, source);
    }

    // Sort children recursively for consistent output
    sortTreeChildren(adapterRootNode);

    rootNodes.push(adapterRootNode);
  }

  return rootNodes;
}

/**
 * Inserts a source into the adapter's tree, creating intermediate folders as needed.
 */
function insertSourceIntoTree(adapterRoot: FileTreeNode, source: SourceSummary): void {
  const parts = source.source_id.split('/').filter(Boolean);

  // Handle empty source_id by placing it directly under adapter root
  if (parts.length === 0) {
    const fileNode: FileTreeNode = {
      name: source.source_id || '(unnamed)',
      path: `${adapterRoot.path}/(unnamed)`,
      type: 'file',
      source,
    };
    adapterRoot.children = adapterRoot.children || [];
    adapterRoot.children.push(fileNode);
    return;
  }

  let currentNode = adapterRoot;

  // Navigate/create folders for all but the last part (the file itself)
  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i];
    const folderPath = `${currentNode.path}/${part}`;

    let childNode = currentNode.children?.find(
      (child) => child.name === part && child.type === 'folder'
    );

    if (!childNode) {
      childNode = {
        name: part,
        path: folderPath,
        type: 'folder',
        children: [],
      };
      currentNode.children = currentNode.children || [];
      currentNode.children.push(childNode);
    }

    currentNode = childNode;
  }

  // Add the file node as the last part
  const fileName = parts[parts.length - 1];
  const filePath = `${currentNode.path}/${fileName}`;

  const fileNode: FileTreeNode = {
    name: fileName,
    path: filePath,
    type: 'file',
    source,
  };

  currentNode.children = currentNode.children || [];
  currentNode.children.push(fileNode);
}

/**
 * Recursively sorts children of a node for consistent tree output.
 * Folders come before files, and both are sorted alphabetically by name.
 */
function sortTreeChildren(node: FileTreeNode): void {
  if (!node.children) return;

  node.children.sort((a, b) => {
    // Folders before files
    if (a.type !== b.type) {
      return a.type === 'folder' ? -1 : 1;
    }
    // Alphabetical by name
    return a.name.localeCompare(b.name);
  });

  // Recursively sort children
  for (const child of node.children) {
    sortTreeChildren(child);
  }
}
