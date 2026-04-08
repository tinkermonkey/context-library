/**
 * Unit tests for file tree building utilities.
 */

import { describe, it, expect } from 'vitest';
import { buildFileTree } from './fileTree';
import type { SourceSummary } from '../types/api';

/**
 * Helper function to create a minimal SourceSummary for testing.
 */
function createSource(sourceId: string, adapterId: string = 'adapter:default'): SourceSummary {
  return {
    source_id: sourceId,
    adapter_id: adapterId,
    adapter_type: 'TestAdapter',
    domain: 'documents',
    origin_ref: `ref-${sourceId}`,
    display_name: sourceId,
    current_version: 1,
    last_fetched_at: null,
    poll_strategy: 'on_demand',
    chunk_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    _links: {},
  };
}

describe('buildFileTree', () => {
  it('returns empty array for empty input', () => {
    const result = buildFileTree([]);
    expect(result).toEqual([]);
  });

  it('creates a single root node for adapter with one file at root', () => {
    const sources = [createSource('file.txt', 'filesystem:a')];
    const result = buildFileTree(sources);

    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      name: 'filesystem:a',
      path: 'filesystem:a',
      type: 'folder',
    });

    const adapterRoot = result[0];
    expect(adapterRoot.children).toHaveLength(1);
    expect(adapterRoot.children![0]).toMatchObject({
      name: 'file.txt',
      path: 'filesystem:a/file.txt',
      type: 'file',
    });
  });

  it('creates nested folder structure from hierarchical source_id', () => {
    const sources = [createSource('projects/alpha/design.md', 'filesystem:a')];
    const result = buildFileTree(sources);

    expect(result).toHaveLength(1);
    const adapterRoot = result[0];
    expect(adapterRoot.name).toBe('filesystem:a');

    // Navigate the tree: filesystem:a -> projects -> alpha -> design.md
    const projectsFolder = adapterRoot.children![0];
    expect(projectsFolder.name).toBe('projects');
    expect(projectsFolder.type).toBe('folder');

    const alphaFolder = projectsFolder.children![0];
    expect(alphaFolder.name).toBe('alpha');
    expect(alphaFolder.type).toBe('folder');

    const designFile = alphaFolder.children![0];
    expect(designFile.name).toBe('design.md');
    expect(designFile.type).toBe('file');
    expect(designFile.source).toBeDefined();
    expect(designFile.source!.source_id).toBe('projects/alpha/design.md');
  });

  it('synthesizes intermediate folder nodes without direct file children', () => {
    const sources = [
      createSource('a/b/c/file1.txt', 'filesystem:a'),
      createSource('a/b/c/file2.txt', 'filesystem:a'),
    ];
    const result = buildFileTree(sources);

    const adapterRoot = result[0];
    const aFolder = adapterRoot.children![0];
    expect(aFolder.name).toBe('a');
    expect(aFolder.type).toBe('folder');
    // aFolder should only have one child (b folder), not the files
    expect(aFolder.children!.length).toBe(1);

    const bFolder = aFolder.children![0];
    expect(bFolder.name).toBe('b');
    expect(bFolder.type).toBe('folder');

    const cFolder = bFolder.children![0];
    expect(cFolder.name).toBe('c');
    expect(cFolder.type).toBe('folder');

    // cFolder should have both files
    expect(cFolder.children!.length).toBe(2);
    expect(cFolder.children![0].name).toBe('file1.txt');
    expect(cFolder.children![1].name).toBe('file2.txt');
  });

  it('groups sources by adapter_id at root level', () => {
    const sources = [
      createSource('file1.txt', 'adapter:a'),
      createSource('file2.txt', 'adapter:b'),
      createSource('file3.txt', 'adapter:a'),
    ];
    const result = buildFileTree(sources);

    expect(result).toHaveLength(2);
    const adapterNames = result.map((n) => n.name).sort();
    expect(adapterNames).toEqual(['adapter:a', 'adapter:b']);

    // adapter:a should have 2 files
    const adapterA = result.find((n) => n.name === 'adapter:a')!;
    expect(adapterA.children).toHaveLength(2);

    // adapter:b should have 1 file
    const adapterB = result.find((n) => n.name === 'adapter:b')!;
    expect(adapterB.children).toHaveLength(1);
  });

  it('sorts children with folders before files, then alphabetically', () => {
    const sources = [
      createSource('zebra.txt', 'filesystem:a'),
      createSource('folder/alpha.txt', 'filesystem:a'),
      createSource('apple.txt', 'filesystem:a'),
      createSource('folder/zulu.txt', 'filesystem:a'),
    ];
    const result = buildFileTree(sources);

    const adapterRoot = result[0];
    const children = adapterRoot.children!;

    // Folders should come first
    expect(children[0].type).toBe('folder');
    expect(children[0].name).toBe('folder');

    // Files should come after, sorted alphabetically
    expect(children[1].type).toBe('file');
    expect(children[1].name).toBe('apple.txt');
    expect(children[2].type).toBe('file');
    expect(children[2].name).toBe('zebra.txt');
  });

  it('deep nesting works correctly', () => {
    const sources = [createSource('a/b/c/d/e/f/deep.txt', 'filesystem:a')];
    const result = buildFileTree(sources);

    let current = result[0];
    expect(current.name).toBe('filesystem:a');

    for (const expectedName of ['a', 'b', 'c', 'd', 'e', 'f']) {
      const next = current.children![0];
      expect(next.name).toBe(expectedName);
      expect(next.type).toBe('folder');
      current = next;
    }

    // Final child should be the file
    const deepFile = current.children![0];
    expect(deepFile.name).toBe('deep.txt');
    expect(deepFile.type).toBe('file');
  });

  it('handles normal nested paths correctly', () => {
    const sources = [createSource('folder/subfolder/file.txt', 'filesystem:a')];
    const result = buildFileTree(sources);

    const adapterRoot = result[0];
    const folderNode = adapterRoot.children![0];
    expect(folderNode.name).toBe('folder');
  });

  it('strips leading and trailing slashes from source_id', () => {
    const sources = [
      createSource('/folder/file1.txt', 'filesystem:a'),
      createSource('folder/file2.txt/', 'filesystem:a'),
      createSource('/folder/subfolder/file3.txt/', 'filesystem:a'),
    ];
    const result = buildFileTree(sources);

    const adapterRoot = result[0];
    const folderNode = adapterRoot.children![0];
    expect(folderNode.name).toBe('folder');
    expect(folderNode.type).toBe('folder');

    // All files should be under the folder, without empty-string nodes
    const fileNames = folderNode.children!.map((child) => child.name).sort();
    expect(fileNames).toEqual(['file1.txt', 'file2.txt', 'subfolder']);

    // Deep nested path should also work correctly
    const subfolderNode = folderNode.children!.find((child) => child.name === 'subfolder')!;
    const deepFile = subfolderNode.children![0];
    expect(deepFile.name).toBe('file3.txt');
    expect(deepFile.type).toBe('file');
  });

  it('preserves source metadata on file nodes', () => {
    const sources = [
      {
        source_id: 'test.md',
        adapter_id: 'adapter:1',
        adapter_type: 'TestAdapter',
        domain: 'documents',
        origin_ref: 'origin-123',
        display_name: 'Test Document',
        current_version: 42,
        last_fetched_at: '2026-02-01T12:00:00Z',
        poll_strategy: 'hourly',
        chunk_count: 100,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-02-01T12:00:00Z',
        _links: { self: '/sources/test.md' },
      } as SourceSummary,
    ];

    const result = buildFileTree(sources);
    const fileNode = result[0].children![0];

    expect(fileNode.source).toEqual(sources[0]);
    expect(fileNode.source!.display_name).toBe('Test Document');
    expect(fileNode.source!.current_version).toBe(42);
  });

  it('builds correct paths for all nodes', () => {
    const sources = [createSource('dir/subdir/file.txt', 'adapter:a')];
    const result = buildFileTree(sources);

    const adapterRoot = result[0];
    expect(adapterRoot.path).toBe('adapter:a');

    const dir = adapterRoot.children![0];
    expect(dir.path).toBe('adapter:a/dir');

    const subdir = dir.children![0];
    expect(subdir.path).toBe('adapter:a/dir/subdir');

    const file = subdir.children![0];
    expect(file.path).toBe('adapter:a/dir/subdir/file.txt');
  });

  it('handles empty source_id gracefully', () => {
    const sources = [createSource('', 'adapter:a')];
    const result = buildFileTree(sources);

    expect(result).toHaveLength(1);
    const adapterRoot = result[0];
    expect(adapterRoot.name).toBe('adapter:a');

    // Empty source_id should create a file node with default name
    expect(adapterRoot.children).toHaveLength(1);
    const fileNode = adapterRoot.children![0];
    expect(fileNode.name).toBe('(unnamed)');
    expect(fileNode.path).toBe('adapter:a/(unnamed)');
    expect(fileNode.type).toBe('file');
    expect(fileNode.source).toBeDefined();
    expect(fileNode.source!.source_id).toBe('');
  });
});
