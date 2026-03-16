import { createRootRoute, createRoute, createRouter } from '@tanstack/react-router'
import RootLayout from './routes/__root'
import DashboardPage from './routes/index'
import BrowserPage from './routes/browser'
import SearchPage from './routes/search'

const rootRoute = createRootRoute({
  component: RootLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: DashboardPage,
})

const browserRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/browser',
  component: BrowserPage,
})

const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/search',
  component: SearchPage,
})

const routeTree = rootRoute.addChildren([indexRoute, browserRoute, searchRoute])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
