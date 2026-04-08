/**
 * File browser page component.
 * Displays a hierarchical file tree organized by adapter and source_id structure.
 */

import { useRouterState } from '@tanstack/react-router';
import { Card } from 'flowbite-react';
import type { FileBrowserPageSearch } from '../router';

function FileBrowserPage() {
  const routerState = useRouterState();
  const { file } = routerState.location.search as FileBrowserPageSearch;

  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold">File Browser</h1>

      <Card>
        <div className="text-gray-600">
          <p>File browser interface coming soon.</p>
          {file && <p className="mt-2 text-sm">Selected file: <code>{file}</code></p>}
        </div>
      </Card>
    </div>
  );
}

export default FileBrowserPage;
