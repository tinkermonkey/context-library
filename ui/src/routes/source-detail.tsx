import type { ReactNode } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { PageHeader, Button } from '@tinkermonkey/heimdall-ui';

export default function SourceDetailPage(): ReactNode {
  const { sourceId } = useParams({ from: '/sources/$sourceId' });
  const navigate = useNavigate();

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Sources"
        title="Source Detail"
        subtitle={sourceId}
      />
      <div className="px-6 py-4">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => navigate({ to: '/sources' })}
        >
          ← Back to Sources
        </Button>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          Source detail view coming soon
        </span>
      </div>
    </div>
  );
}
