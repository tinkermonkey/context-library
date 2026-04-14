import { Suspense } from 'react';
import { Outlet } from '@tanstack/react-router';
import { Layout } from '../components/Layout';
import { ErrorBoundary } from '../components/ErrorBoundary';

function PageLoadingFallback() {
  return (
    <div
      className="flex items-center justify-center h-full min-h-[200px]"
      style={{ color: '#6B7280' }}
    >
      <span className="text-sm">Loading…</span>
    </div>
  );
}

function RootErrorFallback({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex items-center justify-center h-full p-8">
      <div
        className="rounded-lg p-6 w-full max-w-lg"
        style={{ background: '#161616', border: '1px solid #1E1E1E' }}
      >
        <h2 className="text-white font-semibold mb-2">Something went wrong</h2>
        <pre
          className="text-sm rounded p-3 mb-4 overflow-auto max-h-40"
          style={{ background: '#111111', color: '#9CA3AF' }}
        >
          {error.message}
        </pre>
        <button
          onClick={reset}
          className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm rounded-md transition-colors"
        >
          Try Again
        </button>
      </div>
    </div>
  );
}

export default function RootLayout() {
  return (
    <ErrorBoundary fallback={(error, reset) => <RootErrorFallback error={error} reset={reset} />}>
      <Layout>
        <Suspense fallback={<PageLoadingFallback />}>
          <Outlet />
        </Suspense>
      </Layout>
    </ErrorBoundary>
  );
}
