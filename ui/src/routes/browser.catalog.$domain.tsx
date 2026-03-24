import { useParams } from '@tanstack/react-router';
import { getDomainView } from '../views/registry';

/**
 * Generic domain catalog route.
 *
 * Reads the $domain URL param, looks up the catalogPage component from the
 * domain registry, and renders it. Each catalogPage is self-contained and
 * fetches its own data.
 *
 * Accessible at /browser/catalog/<domain> for all six domains.
 * Replaces the previous documents-only /browser/catalog/documents route.
 */
export default function DomainCatalogPage() {
  const { domain } = useParams({ from: '/browser/catalog/$domain' });
  const entry = getDomainView(domain);
  const CatalogPage = entry.catalogPage;

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">{entry.pluralLabel}</h1>
        <p className="text-gray-600">Browse all {entry.pluralLabel.toLowerCase()} in your library</p>
      </div>

      <CatalogPage />
    </div>
  );
}
