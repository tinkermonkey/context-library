import { createRootRoute, createRoute, createRouter } from '@tanstack/react-router'
import { lazy } from 'react'
import { z } from 'zod'
import RootLayout from './routes/__root'
import DashboardPage from './routes/index'
import BrowserPage from './routes/browser'
import BrowserVersionsPage from './routes/browser.versions.$sourceId'
import SearchPage from './routes/search'

// Lazy load DomainViewPage to enable code splitting
const DomainViewPage = lazy(() => import('./routes/browser.view'))

const rootRoute = createRootRoute({
  component: RootLayout,
})

const indexSearchSchema = z
  .object({
    sort: z.string().optional(),
    dir: z.enum(['asc', 'desc']).optional(),
    q: z.string().optional(),
    page: z.number().optional(),
    pageSize: z.number().optional(),
  })
  .passthrough() // Preserve filter_* keys for dynamic facet filtering

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: DashboardPage,
  validateSearch: (search: unknown) => indexSearchSchema.parse(search),
})

export const browserSearchSchema = z
  .object({
    domain: z.string().optional(),
    table: z.string().optional(), // 'sources' | 'chunks' | 'versions'
    adapter_id: z.string().optional(),
    source_id: z.string().optional(),
    selectedSourceId: z.string().optional(),
    selectedVersion: z.number().optional(),
    limit: z.number().optional(),
    offset: z.number().optional(),
    // DataTable parameters
    sort: z.string().optional(),
    dir: z.enum(['asc', 'desc']).optional(),
    q: z.string().optional(),
    page: z.number().optional(),
    pageSize: z.number().optional(),
  })
  .passthrough() // Preserve filter_* keys for dynamic facet filtering

export type BrowserPageSearch = z.infer<typeof browserSearchSchema>

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

const domainViewSearchSchema = z.object({
  healthType: z.string().optional(),
  dateFrom: z.string().optional(),
  dateTo: z.string().optional(),
  status: z.string().optional(),
  priority: z.number().optional(),
  section: z.string().optional(), // TOC anchor for document views
})

export type DomainViewPageSearch = z.infer<typeof domainViewSearchSchema>

const domainViewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/browser/view/$domain/$sourceId',
  component: DomainViewPage,
  validateSearch: (search: unknown) => domainViewSearchSchema.parse(search),
})

const searchSearchSchema = z.object({
  q: z.string().optional(),
  domain: z.string().optional(),
  source_id: z.string().optional(),
  rerank: z.boolean().optional(),
  top_k: z.number().optional(),
})

export type SearchPageSearch = z.infer<typeof searchSearchSchema>

const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/search',
  component: SearchPage,
  validateSearch: (search: unknown) => searchSearchSchema.parse(search),
})

const routeTree = rootRoute.addChildren([indexRoute, browserRoute, browserVersionsRoute, domainViewRoute, searchRoute])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
