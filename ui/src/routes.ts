/**
 * Route tree definition and router creation.
 * Separated to a .ts file to comply with react-refresh/only-export-components.
 */

import { createRootRoute, createRoute, createRouter } from '@tanstack/react-router'
import { lazy } from 'react'
import RootLayout from './routes/__root'
import DashboardPage from './routes/index'
import BrowserPage from './routes/browser'
import BrowserVersionsPage from './routes/browser.versions.$sourceId'
import BrowserFilesPage from './routes/browser.files'
import SearchPage from './routes/search'
import {
  indexSearchSchema,
  browserSearchSchema,
  domainViewSearchSchema,
  domainCatalogSearchSchema,
  searchSearchSchema,
  fileBrowserSearchSchema,
} from './routes-config'

// Lazy load DomainViewPage to enable code splitting
const DomainViewPage = lazy(() => import('./routes/browser.view'))

// Lazy load DomainCatalogPage to enable code splitting
const DomainCatalogPage = lazy(() => import('./routes/browser.catalog.$domain'))

const rootRoute = createRootRoute({
  component: RootLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: DashboardPage,
  validateSearch: (search: unknown) => indexSearchSchema.parse(search),
})

const browserRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/browser',
  component: BrowserPage,
  validateSearch: (search: unknown) => browserSearchSchema.parse(search),
})

const browserVersionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/browser/versions/$sourceId',
  component: BrowserVersionsPage,
})

const browserFilesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/browser/files',
  component: BrowserFilesPage,
  validateSearch: (search: unknown) => fileBrowserSearchSchema.parse(search),
})

const domainViewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/browser/view/$domain/$sourceId',
  component: DomainViewPage,
  validateSearch: (search: unknown) => domainViewSearchSchema.parse(search),
  // Note: domainViewSearchSchema is a superset that includes all possible parameters.
  // Individual domain views will extract only the parameters they need via domain-specific schemas.
})

const domainCatalogRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/browser/catalog/$domain',
  component: DomainCatalogPage,
  validateSearch: (search: unknown) => domainCatalogSearchSchema.parse(search),
})

const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/search',
  component: SearchPage,
  validateSearch: (search: unknown) => searchSearchSchema.parse(search),
})

const routeTree = rootRoute.addChildren([indexRoute, browserRoute, browserVersionsRoute, browserFilesRoute, domainViewRoute, domainCatalogRoute, searchRoute])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
