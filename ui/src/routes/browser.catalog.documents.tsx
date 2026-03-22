import { DocumentCatalogView } from '../views/DocumentCatalogView';

/**
 * Document catalog route.
 * Provides a browsable source-level catalog view for the documents domain.
 * Distinct from the detail view at /browser/view/documents/$sourceId.
 */
export default function DocumentCatalogPage() {
  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Documents</h1>
        <p className="text-gray-600">Browse all documents in your catalog</p>
      </div>

      <DocumentCatalogView sourceId="" chunks={[]} />
    </div>
  );
}
