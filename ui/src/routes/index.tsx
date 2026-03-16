import { useNavigate } from '@tanstack/react-router';
import { Card, Badge, Spinner } from 'flowbite-react';
import type { ColumnDef } from '@tanstack/react-table';
import { useStats } from '../hooks/useStats';
import { useAdapterStats } from '../hooks/useAdapterStats';
import { DataTable } from '../components/DataTable';
import type { AdapterStats } from '../types/api';

/**
 * Dashboard landing page at /
 * Displays domain-level summary cards and adapter-level summary table
 */
export default function DashboardPage() {
  const navigate = useNavigate();

  // Fetch stats data
  const stats = useStats();
  const adapterStats = useAdapterStats();

  // Capitalize domain name for display
  const capitalizeFirstLetter = (str: string) =>
    str.charAt(0).toUpperCase() + str.slice(1);

  // Column definitions for adapter table
  const adapterColumns: ColumnDef<AdapterStats>[] = [
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
      cell: ({ row }) => <span>{row.original.source_count}</span>,
    },
    {
      accessorKey: 'active_chunk_count',
      header: 'Active Chunks',
      size: 150,
      cell: ({ row }) => <span>{row.original.active_chunk_count}</span>,
    },
  ];

  // Fetch function for adapter table (client-side data, no pagination needed)
  const fetchAdapters = async () => {
    if (!adapterStats.data) {
      return { rows: [], total: 0 };
    }
    return {
      rows: adapterStats.data.adapters,
      total: adapterStats.data.adapters.length,
    };
  };

  // Handle adapter row click
  const handleAdapterRowClick = (adapter: AdapterStats) => {
    navigate({
      to: '/browser',
      search: {
        domain: adapter.domain,
        adapter_id: adapter.adapter_id,
      },
    });
  };

  // Handle domain card click
  const handleDomainCardClick = (domain: string) => {
    navigate({
      to: '/browser',
      search: { domain },
    });
  };

  // Loading state for both stats and adapter stats
  if (stats.isLoading || adapterStats.isLoading) {
    return (
      <div className="flex justify-center items-center min-h-screen">
        <div className="text-center">
          <Spinner color="info" size="lg" />
          <p className="mt-4 text-gray-600">Loading dashboard data...</p>
        </div>
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
          />
        ) : (
          <div className="text-gray-600">No adapter data available</div>
        )}
      </section>
    </div>
  );
}
