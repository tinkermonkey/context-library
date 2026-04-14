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
  notesSearchSchema,
  messagesViewSearchSchema,
  eventsViewSearchSchema,
  tasksViewSearchSchema,
  healthViewSearchSchema,
  documentsSearchSchema,
} from './routes-config'

// Lazy load DomainViewPage to enable code splitting
const DomainViewPage = lazy(() => import('./routes/browser.view'))

// Lazy load DomainCatalogPage to enable code splitting
const DomainCatalogPage = lazy(() => import('./routes/browser.catalog.$domain'))

// Lazy load domain views (implemented in later issues)
const NotesPage = lazy(() => import('./routes/notes'))
const MessagesPage = lazy(() => import('./routes/messages'))
const EventsPage = lazy(() => import('./routes/events'))
const TasksPage = lazy(() => import('./routes/tasks'))
const HealthPage = lazy(() => import('./routes/health'))
const DocumentsPage = lazy(() => import('./routes/documents'))
const PeoplePage = lazy(() => import('./routes/people'))
const LocationPage = lazy(() => import('./routes/location'))
const MusicPage = lazy(() => import('./routes/music'))
const AdminPage = lazy(() => import('./routes/admin'))

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

// Domain views (#439–#449)
const notesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/notes',
  component: NotesPage,
  validateSearch: (search: unknown) => notesSearchSchema.parse(search),
})

const messagesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/messages',
  component: MessagesPage,
  validateSearch: (search: unknown) => messagesViewSearchSchema.parse(search),
})

const eventsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/events',
  component: EventsPage,
  validateSearch: (search: unknown) => eventsViewSearchSchema.parse(search),
})

const tasksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/tasks',
  component: TasksPage,
  validateSearch: (search: unknown) => tasksViewSearchSchema.parse(search),
})

const healthRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/health',
  component: HealthPage,
  validateSearch: (search: unknown) => healthViewSearchSchema.parse(search),
})

const documentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/documents',
  component: DocumentsPage,
  validateSearch: (search: unknown) => documentsSearchSchema.parse(search),
})

const peopleRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/people',
  component: PeoplePage,
})

const locationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/location',
  component: LocationPage,
})

const musicRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/music',
  component: MusicPage,
})

const adminRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin',
  component: AdminPage,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  searchRoute,
  notesRoute,
  messagesRoute,
  eventsRoute,
  tasksRoute,
  healthRoute,
  documentsRoute,
  peopleRoute,
  locationRoute,
  musicRoute,
  adminRoute,
  browserRoute,
  browserVersionsRoute,
  browserFilesRoute,
  domainViewRoute,
  domainCatalogRoute,
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
