import { useState } from 'react';
import { useNavigate, useRouterState } from '@tanstack/react-router';
import { Button, Card, TextInput, Select, ToggleSwitch, Spinner, Badge, Progress } from 'flowbite-react';
import { useSearch } from '../hooks/useSearch';
import type { SearchPageSearch } from '../router';
import type { QueryResultItem } from '../types/api';

const DOMAINS = ['messages', 'notes', 'events', 'tasks', 'health', 'documents'] as const;

function SearchResultCard({ result }: { result: QueryResultItem }) {
  const navigate = useNavigate();

  const handleViewInBrowser = () => {
    navigate({
      to: '/browser',
      search: {
        domain: result.domain,
        table: 'chunks',
        source_id: result.source_id,
      },
    });
  };

  const previewText = result.chunk_text.substring(0, 300);
  const hasMore = result.chunk_text.length > 300;

  return (
    <Card className="mb-3">
      <div className="flex justify-between items-start mb-3">
        <div className="flex gap-2">
          <Badge>{result.domain}</Badge>
          <Badge color="gray">{result.chunk_type}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">Score</span>
          <Progress progress={Math.round(result.similarity_score * 100)} size="sm" className="w-24" />
          <span className="text-xs font-medium">{(result.similarity_score * 100).toFixed(0)}%</span>
        </div>
      </div>

      <p className="text-sm text-gray-700 mt-2 line-clamp-3">
        {previewText}
        {hasMore ? '…' : ''}
      </p>

      <div className="flex justify-between items-center mt-4 text-xs text-gray-400">
        <span title={result.source_id}>Source: {result.source_id.substring(0, 20)}…</span>
        <button
          onClick={handleViewInBrowser}
          className="text-blue-600 hover:text-blue-800 hover:underline"
        >
          View in Browser
        </button>
      </div>
    </Card>
  );
}

export default function SearchPage() {
  const navigate = useNavigate();
  const routerState = useRouterState();
  const search = (routerState.location.search ?? {}) as SearchPageSearch;

  const [formState, setFormState] = useState({
    q: search.q ?? '',
    domain: search.domain ?? '',
    source_id: search.source_id ?? '',
    rerank: search.rerank ?? false,
    top_k: search.top_k ?? 10,
  });

  const { data, isLoading, error } = useSearch(search);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formState.q.trim()) return;

    navigate({
      to: '/search',
      search: {
        q: formState.q,
        domain: formState.domain || undefined,
        source_id: formState.source_id || undefined,
        rerank: formState.rerank,
        top_k: formState.top_k,
      },
    });
  };

  const handleClear = () => {
    setFormState({
      q: '',
      domain: '',
      source_id: '',
      rerank: false,
      top_k: 10,
    });
    navigate({
      to: '/search',
      search: {},
    });
  };

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">Semantic Search</h1>
        <p className="text-gray-600">Search across all indexed content by semantic meaning</p>
      </div>

      {/* Search Form */}
      <Card className="mb-8">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="query" className="block text-sm font-medium text-gray-700 mb-2">
              Search Query
            </label>
            <TextInput
              id="query"
              type="text"
              placeholder="What are you looking for?"
              value={formState.q}
              onChange={(e) => setFormState({ ...formState, q: e.target.value })}
              disabled={isLoading}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="domain" className="block text-sm font-medium text-gray-700 mb-2">
                Domain Filter
              </label>
              <Select
                id="domain"
                value={formState.domain}
                onChange={(e) => setFormState({ ...formState, domain: e.target.value })}
                disabled={isLoading}
              >
                <option value="">All domains</option>
                {DOMAINS.map((domain) => (
                  <option key={domain} value={domain}>
                    {domain.charAt(0).toUpperCase() + domain.slice(1)}
                  </option>
                ))}
              </Select>
            </div>

            <div>
              <label htmlFor="source_id" className="block text-sm font-medium text-gray-700 mb-2">
                Source ID Filter
              </label>
              <TextInput
                id="source_id"
                type="text"
                placeholder="Optional source ID"
                value={formState.source_id}
                onChange={(e) => setFormState({ ...formState, source_id: e.target.value })}
                disabled={isLoading}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="top_k" className="block text-sm font-medium text-gray-700 mb-2">
                Results Limit
              </label>
              <TextInput
                id="top_k"
                type="number"
                min="1"
                max="100"
                value={formState.top_k}
                onChange={(e) => setFormState({ ...formState, top_k: parseInt(e.target.value) || 10 })}
                disabled={isLoading}
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <ToggleSwitch
              id="rerank"
              checked={formState.rerank}
              onChange={(checked) => setFormState({ ...formState, rerank: checked })}
              disabled={isLoading}
            />
            <label htmlFor="rerank" className="text-sm font-medium text-gray-700 cursor-pointer">
              Enable Reranking
            </label>
          </div>

          <div className="flex gap-3 pt-2">
            <Button
              type="submit"
              disabled={!formState.q.trim() || isLoading}
              color="blue"
            >
              {isLoading ? (
                <>
                  <Spinner size="sm" className="mr-2" />
                  Searching...
                </>
              ) : (
                'Search'
              )}
            </Button>
            <Button
              type="button"
              onClick={handleClear}
              color="gray"
              disabled={isLoading}
            >
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {/* Error State */}
      {error && (
        <Card className="mb-8 bg-red-50 border border-red-200">
          <div className="text-red-800">
            <p className="font-semibold">Search Error</p>
            <p className="text-sm mt-1">
              {error instanceof Error ? error.message : 'An error occurred while searching'}
            </p>
          </div>
        </Card>
      )}

      {/* Results Section */}
      {search.q ? (
        <>
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-12">
              <Spinner size="lg" className="mb-4" />
              <p className="text-gray-600">Searching...</p>
            </div>
          )}

          {!isLoading && data && (
            <>
              <div className="mb-4">
                <p className="text-sm text-gray-600">
                  Found {data.total} result{data.total !== 1 ? 's' : ''} for "{search.q}"
                </p>
              </div>

              {data.results.length > 0 ? (
                <div>
                  {data.results.map((result) => (
                    <SearchResultCard key={result.chunk_hash} result={result} />
                  ))}
                </div>
              ) : (
                <Card className="text-center py-12">
                  <p className="text-gray-500 text-lg mb-2">No results found</p>
                  <p className="text-gray-400 text-sm">Try adjusting your search query or filters</p>
                </Card>
              )}
            </>
          )}
        </>
      ) : (
        <Card className="text-center py-12">
          <p className="text-gray-500 text-lg mb-2">Ready to search</p>
          <p className="text-gray-400 text-sm">Enter a search query above to get started</p>
        </Card>
      )}
    </div>
  );
}
