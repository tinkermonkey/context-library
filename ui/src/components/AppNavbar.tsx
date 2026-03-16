import { useRouterState, Link } from '@tanstack/react-router';
import { HealthIndicator } from './HealthIndicator';

export function AppNavbar() {
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  const isActive = (path: string) => currentPath === path;

  return (
    <nav className="border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-full flex-wrap items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <div className="text-xl font-semibold text-gray-900">Context Library</div>

        <div className="flex items-center gap-6">
          <div className="hidden gap-6 md:flex">
            <Link
              to="/"
              className={`${
                isActive('/') ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-700 hover:text-gray-900'
              } pb-1 font-medium transition-colors`}
            >
              Dashboard
            </Link>
            <Link
              to="/browser"
              className={`${
                isActive('/browser') ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-700 hover:text-gray-900'
              } pb-1 font-medium transition-colors`}
            >
              Data Browser
            </Link>
            <Link
              to="/search"
              className={`${
                isActive('/search') ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-700 hover:text-gray-900'
              } pb-1 font-medium transition-colors`}
            >
              Semantic Search
            </Link>
          </div>

          <HealthIndicator />
        </div>
      </div>
    </nav>
  );
}
