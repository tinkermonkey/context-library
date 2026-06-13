/**
 * Router type exports.
 * The actual router instance is created in routes.ts to comply with react-refresh rules.
 */

export type {
  BrowserPageSearch,
  DomainViewPageSearch,
  SearchPageSearch,
  FileBrowserPageSearch,
  SourcesPageSearch,
} from './routes-config'
export { router } from './routes'
