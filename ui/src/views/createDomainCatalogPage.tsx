import type { ComponentType } from 'react';
import type { CatalogCardProps } from '../components/catalog/BaseCatalogCard';
import { BaseCatalogView } from './BaseCatalogView';

/**
 * Factory: returns a zero-prop React component that renders BaseCatalogView
 * for the given domain with an optional custom card.
 *
 * Used by the domain registry so catalog pages are self-contained and require
 * no props from the route dispatcher.
 */
export function createDomainCatalogPage(
  domain: string,
  CardComponent?: ComponentType<CatalogCardProps>,
): ComponentType {
  function DomainCatalogPage() {
    return <BaseCatalogView domain={domain} CardComponent={CardComponent} />;
  }
  DomainCatalogPage.displayName = `CatalogPage(${domain})`;
  return DomainCatalogPage;
}
