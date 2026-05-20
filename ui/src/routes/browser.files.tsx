/**
 * File browser page component.
 * Displays a resizable two-column layout: file tree (left) and content (right).
 *
 * Fetches chunks once at the parent level to avoid duplicate requests in child panels.
 */

import { useRouterState } from '@tanstack/react-router';
import { SplitPane } from '@tinkermonkey/heimdall-ui';
import { FileTreePanel } from '../components/filebrowser/FileTreePanel';
import { FileContentPanel } from '../components/filebrowser/FileContentPanel';
import { FileMetadataPanel } from '../components/filebrowser/FileMetadataPanel';
import { useSourceChunks } from '../hooks/useChunks';
import { fileBrowserSearchSchema } from '../routes-config';

function FileBrowserPage() {
  const routerState = useRouterState();
  const parseResult = fileBrowserSearchSchema.safeParse(routerState.location.search);
  const { file } = parseResult.success ? parseResult.data : { file: undefined };
  const selectedSourceId = file ?? null;

  // Fetch chunks once at parent level to share between child panels
  const { data: chunksData, isLoading, isError, error } = useSourceChunks(
    selectedSourceId ?? '',
    undefined,
    undefined,
    undefined,
    !!selectedSourceId
  );

  const chunks = chunksData?.chunks;

  const fileTreePanel = (
    <div className="h-full bg-white">
      <FileTreePanel selectedSourceId={selectedSourceId} />
    </div>
  );

  const contentPanel = (
    <div className="flex h-full bg-white overflow-hidden">
      {/* File content */}
      <div className="flex-1 overflow-y-auto p-6">
        <FileContentPanel
          selectedSourceId={selectedSourceId}
          chunks={chunks}
          isLoading={isLoading}
          isError={isError}
          error={error instanceof Error ? error : null}
        />
      </div>

      {/* Metadata panel */}
      <div className="w-72 border-l border-blue-500 bg-white overflow-y-auto p-6 flex flex-col gap-4 shrink-0">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-gray-900">Metadata</h2>
          <p className="text-sm text-gray-500">File information and details</p>
        </div>
        <FileMetadataPanel
          selectedSourceId={selectedSourceId}
          chunks={chunks}
          isLoading={isLoading}
          isError={isError}
          error={error instanceof Error ? error : null}
        />
      </div>
    </div>
  );

  return (
    <div className="flex flex-col bg-gray-50 h-full overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 bg-white shrink-0">
        <h1 className="text-3xl font-bold text-gray-900">File Browser</h1>
      </div>

      {/* Resizable layout: File tree and content */}
      <div className="flex-1 overflow-hidden">
        <SplitPane
          direction="horizontal"
          initialSplitPercent={25}
          minSize={200}
          first={fileTreePanel}
          second={contentPanel}
        />
      </div>
    </div>
  );
}

export default FileBrowserPage;
