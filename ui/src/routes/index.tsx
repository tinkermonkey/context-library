import { useNavigate } from '@tanstack/react-router';
import { Card, Badge, Button } from 'flowbite-react';
import { useMemo, useCallback, useState } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { useStats } from '../hooks/useStats';
import { useAdapterStats } from '../hooks/useAdapterStats';
import { DataTable } from '../components/DataTable';
import { ResetAdapterDialog } from '../components/ResetAdapterDialog';
import type { AdapterStats } from '../types/api';

// Capitalize domain name for display
const capitalizeFirstLetter = (str: string) =>
  str.charAt(0).toUpperCase() + str.slice(1);

// Skeleton placeholder for domain cards
const DomainCardSkeleton = () => (
  <Card className="animate-pulse">
    <div className="h-6 bg-gray-300 rounded w-24 mb-4"></div>
    <div className="space-y-2">
      <div className="h-8 bg-gray-300 rounded w-32"></div>
      <div className="h-8 bg-gray-300 rounded w-32"></div>
    </div>
  </Card>
);

// Skeleton placeholder for table rows
const TableSkeletonRows = () => (
  <div className="space-y-2">
    {[...Array(5)].map((_, i) => (
      <div
        key={i}
        className="flex gap-4 p-4 border rounded-lg animate-pulse"
      >
        <div className="flex-1 h-6 bg-gray-300 rounded"></div>
        <div className="flex-1 h-6 bg-gray-300 rounded"></div>
        <div className="flex-1 h-6 bg-gray-300 rounded"></div>
        <div className="flex-1 h-6 bg-gray-300 rounded"></div>
        <div className="flex-1 h-6 bg-gray-300 rounded"></div>
      </div>
    ))}
  </div>
);

/**
 * Dashboard landing page at /
 * Displays domain-level summary cards and adapter-level summary table
 */
export default function DashboardPage() {
  const navigate = useNavigate();
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [selectedAdapter, setSelectedAdapter] = useState<AdapterStats | null>(null);

  // Fetch stats data
  const stats = useStats();
  const adapterStats = useAdapterStats();

  // Column definitions for adapter table (memoized to prevent re-creation on each render)
  const adapterColumns = useMemo<ColumnDef<AdapterStats>[]>(
    () => [
      {
        accessorKey: 'adapter_id',
        header: 'Adapter ID',
        size: 200,
      },
      {
        accessorKey: 'adapter_type',
        header: 'Type',
        size: 150,
      },
      {
        accessorKey: 'domain',
        header: 'Domain',
        size: 150,
      },
      {
        accessorKey: 'source_count',
        header: 'Sources',
        size: 100,
      },
      {
        accessorKey: 'active_chunk_count',
        header: 'Active Chunks',
        size: 150,
      },
      {
        id: 'actions',
        header: 'Actions',
        size: 100,
        cell: ({ row }) => (
          <Button
            size="sm"
            color="failure"
            onClick={(e) => {
              e.stopPropagation();
              setSelectedAdapter(row.original);
              setResetDialogOpen(true);
            }}
          >
            Reset
          </Button>
        ),
      },
    ],
    []
  );

  // Fetch function for adapter table (memoized with useCallback to stabilize reference)
  const fetchAdapters = useCallback(async () => {
    if (!adapterStats.data) {
      return { rows: [], total: 0 };
    }
    return {
      rows: adapterStats.data.adapters,
      total: adapterStats.data.adapters.length,
    };
  }, [adapterStats.data]);

  // Handle adapter row click (navigate with domain to pre-select the domain tab)
  const handleAdapterRowClick = (adapter: AdapterStats) => {
    navigate({
      to: '/browser',
      search: {
        domain: adapter.domain,
        adapter_id: adapter.adapter_id,
      },
    });
  };

  // Handle domain card click (navigate with domain to pre-select the domain tab)
  const handleDomainCardClick = (domain: string) => {
    navigate({
      to: '/browser',
      search: { domain },
    });
  };

  // Loading state for stats with skeleton placeholders
  if (stats.isLoading) {
    return (
      <div className="space-y-8 p-8">
        <div>
          <h1 className="text-4xl font-bold">Dashboard</h1>
          <p className="mt-2 text-gray-600">Overview of data sources and content</p>
        </div>

        <section>
          <h2 className="text-2xl font-semibold mb-6">Domain Summary</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[...Array(5)].map((_, i) => (
              <DomainCardSkeleton key={i} />
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-2xl font-semibold mb-6">Adapter Summary</h2>
          <TableSkeletonRows />
        </section>
      </div>
    );
  }

  // Loading state for adapter stats with skeleton table
  if (adapterStats.isLoading) {
    return (
      <div className="space-y-8 p-8">
        <div>
          <h1 className="text-4xl font-bold">Dashboard</h1>
          <p className="mt-2 text-gray-600">Overview of data sources and content</p>
        </div>

        <section>
          <h2 className="text-2xl font-semibold mb-6">Domain Summary</h2>
          {stats.data?.by_domain ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {stats.data.by_domain.map((domain) => (
                <Card
                  key={domain.domain}
                  className="cursor-pointer hover:shadow-lg transition-shadow"
                  onClick={() => handleDomainCardClick(domain.domain)}
                >
                  <h3 className="text-xl font-semibold">
                    {capitalizeFirstLetter(domain.domain)}
                  </h3>
                  <div className="mt-4 space-y-2">
                    <Badge color="blue" size="lg">
                      {domain.source_count} source{domain.source_count !== 1 ? 's' : ''}
                    </Badge>
                    <Badge color="green" size="lg">
                      {domain.active_chunk_count} chunk
                      {domain.active_chunk_count !== 1 ? 's' : ''}
                    </Badge>
                  </div>
                </Card>
              ))}
            </div>
          ) : null}
        </section>

        <section>
          <h2 className="text-2xl font-semibold mb-6">Adapter Summary</h2>
          <TableSkeletonRows />
        </section>
      </div>
    );
  }

  // Error state for stats
  if (stats.isError) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          <strong>Error loading stats:</strong> {stats.error?.message || 'Unknown error'}
        </div>
      </div>
    );
  }

  // Error state for adapter stats
  if (adapterStats.isError) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          <strong>Error loading adapter stats:</strong>{' '}
          {adapterStats.error?.message || 'Unknown error'}
        </div>
      </div>
    );
  }

  const domainData = stats.data?.by_domain ?? [];

  const handleResetDialogClose = () => {
    setResetDialogOpen(false);
    setSelectedAdapter(null);
  };

  return (
    <div className="space-y-8 p-8">
      <div>
        <h1 className="text-4xl font-bold">Dashboard</h1>
        <p className="mt-2 text-gray-600">Overview of data sources and content</p>
      </div>

      {/* Domain Summary Cards Section */}
      <section>
        <h2 className="text-2xl font-semibold mb-6">Domain Summary</h2>

        {domainData.length === 0 ? (
          <div className="text-gray-600">No domain data available</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {domainData.map((domain) => (
              <Card
                key={domain.domain}
                className="cursor-pointer hover:shadow-lg transition-shadow"
                onClick={() => handleDomainCardClick(domain.domain)}
              >
                <h3 className="text-xl font-semibold">
                  {capitalizeFirstLetter(domain.domain)}
                </h3>
                <div className="mt-4 space-y-2">
                  <Badge color="blue" size="lg">
                    {domain.source_count} source{domain.source_count !== 1 ? 's' : ''}
                  </Badge>
                  <Badge color="green" size="lg">
                    {domain.active_chunk_count} chunk
                    {domain.active_chunk_count !== 1 ? 's' : ''}
                  </Badge>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* Adapter Summary Table Section */}
      <section>
        <h2 className="text-2xl font-semibold mb-6">Adapter Summary</h2>

        {adapterStats.data?.adapters && adapterStats.data.adapters.length > 0 ? (
          <DataTable<AdapterStats>
            columns={adapterColumns}
            fetchFn={fetchAdapters}
            onRowClick={handleAdapterRowClick}
            rowKey={(row) => row.adapter_id}
            queryKey="dashboard-adapters"
            defaultPageSize={25}
            searchable={false}
            onSearchParamsChange={() => {
              // No-op: this table doesn't use URL search parameters
            }}
          />
        ) : (
          <div className="text-gray-600">No adapter data available</div>
        )}
      </section>

      {/* Reset Adapter Dialog */}
      {selectedAdapter && (
        <ResetAdapterDialog
          adapterId={selectedAdapter.adapter_id}
          adapterName={selectedAdapter.adapter_id}
          isOpen={resetDialogOpen}
          onClose={handleResetDialogClose}
        />
      )}
    </div>
  );
}
