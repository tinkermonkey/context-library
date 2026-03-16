import { createRootRoute, createRoute, createRouter } from '@tanstack/react-router'
import { z } from 'zod'
import RootLayout from './routes/__root'
import DashboardPage from './routes/index'
import BrowserPage from './routes/browser'
import SearchPage from './routes/search'

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
    table: z.string().optional(), // 'sources' | 'chunks'
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

const searchSearchSchema = z.object({
  q: z.string().optional(),
  domain: z.string().optional(),
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

const routeTree = rootRoute.addChildren([indexRoute, browserRoute, searchRoute])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
