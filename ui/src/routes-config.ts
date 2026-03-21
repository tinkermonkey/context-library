/**
 * Route schemas and configuration.
 * Separated from router.tsx to comply with react-refresh/only-export-components.
 */

import { z } from 'zod';

export const indexSearchSchema = z
  .object({
    sort: z.string().optional(),
    dir: z.enum(['asc', 'desc']).optional(),
    q: z.string().optional(),
    page: z.number().optional(),
    pageSize: z.number().optional(),
  })
  .passthrough(); // Preserve filter_* keys for dynamic facet filtering

export const browserSearchSchema = z
  .object({
    domain: z.string().optional(),
    table: z.string().optional(), // 'sources' | 'chunks' | 'versions'
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
  .passthrough(); // Preserve filter_* keys for dynamic facet filtering

export type BrowserPageSearch = z.infer<typeof browserSearchSchema>;

export const domainViewSearchSchema = z.object({
  thread_id: z.string().optional(), // Messages domain: filter to specific thread
  healthType: z.string().optional(),
  dateFrom: z.string().optional(),
  dateTo: z.string().optional(),
  status: z.string().optional(),
  priority: z.number().optional(),
  section: z.string().optional(), // TOC anchor for document/notes views
  documentType: z.string().optional(), // Document type filter for documents domain catalog
});

export type DomainViewPageSearch = z.infer<typeof domainViewSearchSchema>;

// Domain-specific search schemas for runtime parsing and parameter stripping
export const messagesViewSearchSchema = z.object({
  thread_id: z.string().optional(),
});

export type MessagesViewPageSearch = z.infer<typeof messagesViewSearchSchema>;

export const healthViewSearchSchema = z.object({
  healthType: z.string().optional(),
  dateFrom: z.string().optional(),
  dateTo: z.string().optional(),
});

export type HealthViewPageSearch = z.infer<typeof healthViewSearchSchema>;

export const eventsViewSearchSchema = z.object({
  dateFrom: z.string().optional(),
  dateTo: z.string().optional(),
});

export type EventsViewPageSearch = z.infer<typeof eventsViewSearchSchema>;

export const tasksViewSearchSchema = z.object({
  status: z.string().optional(),
  priority: z.number().optional(),
});

export type TasksViewPageSearch = z.infer<typeof tasksViewSearchSchema>;

export const documentCatalogSearchSchema = z.object({
  documentType: z.string().optional(), // Document type filter for documents domain catalog
});

export type DocumentCatalogPageSearch = z.infer<typeof documentCatalogSearchSchema>;

export const searchSearchSchema = z.object({
  q: z.string().optional(),
  domain: z.string().optional(),
  source_id: z.string().optional(),
  rerank: z.boolean().optional(),
  top_k: z.number().optional(),
});

export type SearchPageSearch = z.infer<typeof searchSearchSchema>;
