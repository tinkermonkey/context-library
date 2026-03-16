/**
 * Generic, reusable DataTable component powered by TanStack Table.
 * Handles sorting, global search, facet filtering, pagination, row expansion,
 * and synchronization of all state with TanStack Router URL search parameters.
 *
 * Generic over row data type TData.
 */

import { useCallback, useMemo, useState } from 'react';
import { useNavigate, useRouterState } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import {
  useReactTable,
  getCoreRowModel,
  type ColumnDef,
  type SortingState,
  type PaginationState,
} from '@tanstack/react-table';
import { TextInput, Button, Spinner } from 'flowbite-react';
import { ChevronLeftIcon, ChevronRightIcon, ChevronUpIcon, ChevronDownIcon } from '@heroicons/react/24/outline';

/**
 * Fetch parameters passed to the data-fetching function.
 */
export interface FetchParams {
  sortColumn?: string;
  sortDir?: 'asc' | 'desc';
  search?: string;
  filters?: Record<string, string[]>;
  page: number;
  pageSize: number;
}

/**
 * Facet configuration for a column with constrained values.
 */
export interface FacetConfig {
  column: string;
  label: string;
  values: string[];
}

/**
 * Props for the DataTable component.
 */
export interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[];
  fetchFn: (params: FetchParams) => Promise<{ rows: TData[]; total: number }>;
  facets?: FacetConfig[];
  searchable?: boolean;
  onRowClick?: (row: TData) => void;
  renderDetail?: (row: TData) => React.ReactNode;
  defaultPageSize?: number;
  rowKey: (row: TData) => string;
  queryKey: string; // For cache namespacing
}

/**
 * Generic DataTable component with integrated TanStack Table, Router, and React Query.
 */
export function DataTable<TData>({
  columns,
  fetchFn,
  facets,
  searchable = true,
  onRowClick,
  renderDetail,
  defaultPageSize = 25,
  rowKey,
  queryKey,
}: DataTableProps<TData>) {
  const navigate = useNavigate();
  const routerState = useRouterState();

  // Safely parse URL search params into table state
  const params = (routerState.location.search ?? {}) as Record<string, unknown>;
  const sortColumn = (typeof params.sort === 'string' ? params.sort : undefined) ?? undefined;
  const sortDir = (typeof params.dir === 'string' && (params.dir === 'asc' || params.dir === 'desc') ? params.dir : undefined) ?? undefined;
  const searchQuery = (typeof params.q === 'string' ? params.q : '') ?? '';
  const currentPage = Math.max(0, parseInt((typeof params.page === 'string' ? params.page : '0'), 10) || 0);
  const pageSize = Math.max(10, parseInt((typeof params.pageSize === 'string' ? params.pageSize : String(defaultPageSize)), 10) || defaultPageSize);

  // Parse facet filters from URL (filter_<column>=value1,value2,...)
  const filters: Record<string, string[]> = useMemo(() => {
    const filterObj: Record<string, string[]> = {};
    if (facets) {
      for (const facet of facets) {
        const filterKey = `filter_${facet.column}`;
        const filterValue = params[filterKey];
        if (typeof filterValue === 'string' && filterValue.length > 0) {
          filterObj[facet.column] = filterValue.split(',').filter(v => v.length > 0);
        }
      }
    }
    return filterObj;
  }, [params, facets]);

  // Local state for expanded row
  const [expandedRowKey, setExpandedRowKey] = useState<string | null>(null);

  // Fetch data based on current table state
  const { data: queryData, isLoading, isError, error } = useQuery({
    queryKey: [queryKey, { sortColumn, sortDir, search: searchQuery, filters, page: currentPage, pageSize }],
    queryFn: () =>
      fetchFn({
        sortColumn,
        sortDir,
        search: searchQuery,
        filters: Object.keys(filters).length > 0 ? filters : undefined,
        page: currentPage,
        pageSize,
      }),
    staleTime: 10_000,
  });

  // TanStack Table state
  const sorting: SortingState = sortColumn
    ? [{ id: sortColumn, desc: sortDir === 'desc' }]
    : [];
  const pagination: PaginationState = {
    pageIndex: currentPage,
    pageSize,
  };

  // Sorting handler with 3-click cycle: asc → desc → none
  const handleSort = useCallback(
    (columnId: string) => {
      let newSort = sortColumn === columnId ? sortDir : undefined;

      if (newSort === undefined) {
        // First click: ascending
        newSort = 'asc';
      } else if (newSort === 'asc') {
        // Second click: descending
        newSort = 'desc';
      } else {
        // Third click: clear sort
        newSort = undefined;
      }

      const newParams: Record<string, unknown> = { ...params, page: 0 };

      if (newSort !== undefined) {
        newParams.sort = columnId;
        newParams.dir = newSort;
      } else {
        delete newParams.sort;
        delete newParams.dir;
      }

      navigate({ search: newParams as any });
    },
    [sortColumn, sortDir, params, navigate]
  );

  // Search handler
  const handleSearch = useCallback(
    (query: string) => {
      const newParams: Record<string, unknown> = { ...params, page: 0 };
      if (query && query.trim()) {
        newParams.q = query;
      } else {
        delete newParams.q;
      }
      navigate({ search: newParams as any });
    },
    [params, navigate]
  );

  // Facet filter handler
  const handleFacetChange = useCallback(
    (column: string, values: string[]) => {
      const newParams: Record<string, unknown> = { ...params, page: 0 };
      const filterKey = `filter_${column}`;

      if (values.length > 0) {
        newParams[filterKey] = values.join(',');
      } else {
        delete newParams[filterKey];
      }

      navigate({ search: newParams as any });
    },
    [params, navigate]
  );

  // Pagination handlers
  const handlePrevPage = useCallback(() => {
    if (currentPage > 0) {
      navigate({ search: { ...params, page: currentPage - 1 } as any });
    }
  }, [currentPage, params, navigate]);

  const handleNextPage = useCallback(() => {
    const total = queryData?.total ?? 0;
    const maxPage = Math.ceil(total / pageSize) - 1;
    if (currentPage < maxPage) {
      navigate({ search: { ...params, page: currentPage + 1 } as any });
    }
  }, [currentPage, pageSize, queryData?.total, params, navigate]);

  const handlePageSizeChange = useCallback(
    (size: string) => {
      const newParams: Record<string, unknown> = { ...params, page: 0 };
      newParams.pageSize = parseInt(size, 10);
      navigate({ search: newParams as any });
    },
    [params, navigate]
  );

  // Row click handler
  const handleRowClick = useCallback(
    (row: TData) => {
      if (renderDetail) {
        setExpandedRowKey(expandedRowKey === rowKey(row) ? null : rowKey(row));
      } else if (onRowClick) {
        onRowClick(row);
      }
    },
    [expandedRowKey, rowKey, renderDetail, onRowClick]
  );

  // Initialize TanStack Table
  const table = useReactTable({
    data: queryData?.rows ?? [],
    columns,
    state: {
      sorting,
      pagination,
    },
    pageCount: Math.ceil((queryData?.total ?? 0) / pageSize),
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualFiltering: true,
    manualPagination: true,
  });

  const rows = table.getRowModel().rows;
  const total = queryData?.total ?? 0;
  const startRecord = currentPage * pageSize + 1;
  const endRecord = Math.min((currentPage + 1) * pageSize, total);

  // Render loading state
  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-12">
        <Spinner color="info" size="lg" />
      </div>
    );
  }

  // Render error state
  if (isError) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        <strong>Error loading data:</strong> {error?.message || 'Unknown error'}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Search and Facet Filters */}
      <div className="space-y-3">
        {searchable && (
          <TextInput
            type="search"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full"
          />
        )}

        {facets && facets.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {facets.map((facet) => (
              <div key={facet.column} className="flex flex-col gap-1">
                <label className="text-sm font-medium text-gray-700">{facet.label}</label>
                <select
                  multiple
                  value={filters[facet.column] ?? []}
                  onChange={(e) => {
                    const selectedOptions = Array.from(e.target.selectedOptions, (o) => o.value);
                    handleFacetChange(facet.column, selectedOptions);
                  }}
                  className="w-full rounded border border-gray-300 p-2 text-sm"
                >
                  {facet.values.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Record Count Summary */}
      <div className="text-sm text-gray-600">
        {total === 0 ? 'No records' : `Showing ${startRecord}–${endRecord} of ${total} records`}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse border border-gray-300">
          <thead className="bg-gray-100">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    onClick={() => header.column.getCanSort() && handleSort(header.column.id)}
                    className={`border border-gray-300 px-4 py-2 text-left font-semibold text-gray-700 ${
                      header.column.getCanSort() ? 'cursor-pointer select-none hover:bg-gray-200' : ''
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {header.isPlaceholder ? null : (
                        <>
                          {header.column.columnDef.header &&
                            (typeof header.column.columnDef.header === 'function'
                              ? header.column.columnDef.header(header.getContext())
                              : header.column.columnDef.header)}
                          {header.column.getCanSort() && (
                            <span className="text-gray-400">
                              {sortColumn === header.column.id ? (
                                sortDir === 'asc' ? (
                                  <ChevronUpIcon className="h-4 w-4" />
                                ) : (
                                  <ChevronDownIcon className="h-4 w-4" />
                                )
                              ) : (
                                <span className="text-xs">⇅</span>
                              )}
                            </span>
                          )}
                        </>
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>

          <tbody className="divide-y divide-gray-300">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="border border-gray-300 px-4 py-4 text-center text-gray-500">
                  No rows to display
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const isExpanded = expandedRowKey === rowKey(row.original);
                return (
                  <tbody key={rowKey(row.original)}>
                    <tr
                      onClick={() => (renderDetail || onRowClick) && handleRowClick(row.original)}
                      className={`hover:bg-gray-50 ${(renderDetail || onRowClick) ? 'cursor-pointer' : ''}`}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="border border-gray-300 px-4 py-2 text-gray-900">
                          {cell.column.columnDef.cell &&
                            (typeof cell.column.columnDef.cell === 'function'
                              ? cell.column.columnDef.cell(cell.getContext())
                              : cell.column.columnDef.cell)}
                        </td>
                      ))}
                    </tr>

                    {isExpanded && renderDetail && (
                      <tr className="bg-gray-50">
                        <td colSpan={columns.length} className="border border-gray-300 px-4 py-4">
                          {renderDetail(row.original)}
                        </td>
                      </tr>
                    )}
                  </tbody>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 border-t pt-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Page size:</label>
          <select
            value={String(pageSize)}
            onChange={(e) => handlePageSizeChange(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1 text-sm"
          >
            {[10, 25, 50, 100].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">
            Page {currentPage + 1} of {Math.ceil(total / pageSize) || 1}
          </span>
        </div>

        <div className="flex gap-2">
          <Button
            onClick={handlePrevPage}
            disabled={currentPage === 0}
            size="sm"
            color="light"
            className="flex items-center gap-1"
          >
            <ChevronLeftIcon className="h-4 w-4" />
            Previous
          </Button>
          <Button
            onClick={handleNextPage}
            disabled={currentPage >= Math.ceil(total / pageSize) - 1}
            size="sm"
            color="light"
            className="flex items-center gap-1"
          >
            Next
            <ChevronRightIcon className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
