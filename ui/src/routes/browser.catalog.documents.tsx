import type { SourceDetailResponse } from '../types/api';
import { DocumentCatalogView } from '../views/DocumentCatalogView';

/**
 * Document catalog route.
 * Provides a browsable source-level catalog view for the documents domain.
 * Distinct from the detail view at /browser/view/documents/$sourceId.
 */
export default function DocumentCatalogPage() {
  // Create a minimal SourceDetailResponse for catalog view
  // The catalog view fetches its own source list and doesn't use these props
  const dummySource: SourceDetailResponse = {
    source_id: '',
    adapter_id: '',
    adapter_type: '',
    domain: 'documents',
    origin_ref: '',
    display_name: null,
    current_version: 0,
    chunk_count: 0,
    poll_strategy: '',
    last_fetched_at: null,
    created_at: '',
    updated_at: '',
    poll_interval_sec: null,
    normalizer_version: '',
    _links: {},
  };

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Documents</h1>
        <p className="text-gray-600">Browse all documents in your catalog</p>
      </div>

      <DocumentCatalogView sourceId="" chunks={[]} source={dummySource} />
    </div>
  );
}
