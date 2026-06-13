import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { UsersIcon } from '@heroicons/react/24/outline';
import { Icon, PageHeader, Avatar, ActivityTimeline, GraphCanvas, GraphNode } from '@tinkermonkey/heimdall-ui';
import type { ActivityEvent, GraphNodeData, GraphEdgeData } from '@tinkermonkey/heimdall-ui';
import { AlphabetIndex } from '../components/AlphabetIndex';
import { FilterDropdown } from '../components/FilterDropdown';
import { useSources } from '../hooks/useSources';
import { postQuery, fetchSourceChunks } from '../api/client';
import { getDomainColor, getDomainColorWithAlpha } from '../lib/designTokens';
import type { SourceSummary, QueryResultItem } from '../types/api';

const peopleColor = getDomainColor('people');
const EMPTY_SOURCES: SourceSummary[] = [];

// ── People metadata ────────────────────────────────────────────────

interface PeopleMeta {
  contact_id: string;
  display_name: string;
  organization: string | null;
  job_title: string | null;
  source_type: string;
}

function extractPeopleMeta(domainMetadata: unknown): PeopleMeta | null {
  if (!domainMetadata || typeof domainMetadata !== 'object') return null;
  const dm = domainMetadata as Record<string, unknown>;
  return {
    contact_id: typeof dm.contact_id === 'string' ? dm.contact_id : '',
    display_name: typeof dm.display_name === 'string' ? dm.display_name : 'Unknown',
    organization: typeof dm.organization === 'string' ? dm.organization : null,
    job_title: typeof dm.job_title === 'string' ? dm.job_title : null,
    source_type: typeof dm.source_type === 'string' ? dm.source_type : 'contacts',
  };
}

// ── Source badge label ─────────────────────────────────────────────

function adapterLabel(adapterId: string): string {
  if (adapterId.includes('apple_contacts') || adapterId.includes('apple_address')) return 'Apple Contacts';
  if (adapterId.includes('google_contacts')) return 'Google Contacts';
  if (adapterId.includes('vcard')) return 'vCard';
  const base = adapterId.replace(/:default$/, '').replace(/_/g, ' ');
  return base.charAt(0).toUpperCase() + base.slice(1);
}

// ── Contact Card ───────────────────────────────────────────────────

function ContactCard({
  source,
  isSelected,
  onClick,
}: {
  source: SourceSummary;
  isSelected: boolean;
  onClick: () => void;
}): ReactNode {
  const name = source.display_name ?? source.origin_ref;
  const label = adapterLabel(source.adapter_id);

  return (
    <button
      onClick={onClick}
      className="text-left flex flex-col gap-2.5 transition-colors"
      style={{
        width: 192,
        padding: 16,
        background: isSelected ? getDomainColorWithAlpha('people', '18') : 'rgb(var(--canvas-surface))',
        border: `1px solid ${isSelected ? peopleColor : 'rgb(var(--canvas-border))'}`,
        borderRadius: 8,
        flexShrink: 0,
      }}
    >
      <Avatar name={name} size="md" />
      <div className="flex flex-col gap-0.5 min-w-0 w-full">
        <span
          className="text-sm font-semibold truncate"
          style={{ color: 'rgb(var(--canvas-fg-1))' }}
        >
          {name}
        </span>
      </div>
      <div
        className="flex items-center self-start"
        style={{ background: 'rgb(var(--canvas-border))', borderRadius: 4, padding: '3px 8px' }}
      >
        <span className="text-[10px]" style={{ color: 'rgb(var(--canvas-fg-3))' }}>{label}</span>
      </div>
    </button>
  );
}

// ── Detail Panel ───────────────────────────────────────────────────

function DetailPanel({
  source,
  onGoToMessages,
  onGoToEvents,
}: {
  source: SourceSummary;
  onGoToMessages: () => void;
  onGoToEvents: () => void;
}): ReactNode {
  const name = source.display_name ?? source.origin_ref;
  const label = adapterLabel(source.adapter_id);

  const { data: chunksData } = useQuery({
    queryKey: ['source-chunks-people', source.source_id],
    queryFn: () => fetchSourceChunks(source.source_id, undefined, 1, 0),
    staleTime: 60_000,
  });

  const meta = useMemo((): PeopleMeta | null => {
    const firstChunk = chunksData?.chunks?.[0];
    if (!firstChunk) return null;
    return extractPeopleMeta(firstChunk.domain_metadata);
  }, [chunksData]);

  const roleLabel = meta?.job_title
    ? meta.organization
      ? `${meta.job_title} · ${meta.organization}`
      : meta.job_title
    : meta?.organization ?? null;

  const messagesQuery = useQuery({
    queryKey: ['people-messages', source.source_id, name],
    queryFn: () =>
      postQuery({ query: name, top_k: 5, domain_filter: 'messages', source_filter: null, rerank: false }),
    enabled: !!name,
    staleTime: 60_000,
  });

  const eventsQuery = useQuery({
    queryKey: ['people-events', source.source_id, name],
    queryFn: () =>
      postQuery({ query: name, top_k: 3, domain_filter: 'events', source_filter: null, rerank: false }),
    enabled: !!name,
    staleTime: 60_000,
  });

  const timelineEvents = useMemo((): ActivityEvent[] => {
    const now = new Date().toISOString();
    const msgItems: QueryResultItem[] = messagesQuery.data?.results ?? [];
    const evtItems: QueryResultItem[] = eventsQuery.data?.results ?? [];

    const msgEvents: ActivityEvent[] = msgItems.map(item => ({
      id: `msg-${item.chunk_hash}`,
      type: 'update' as const,
      subject: item.chunk_text.split('\n')[0].slice(0, 80) || 'Message',
      timestamp: now,
      meta: adapterLabel(item.adapter_id),
      onClick: onGoToMessages,
    }));

    const evtEvents: ActivityEvent[] = evtItems.map(item => ({
      id: `evt-${item.chunk_hash}`,
      type: 'run' as const,
      subject: item.chunk_text.split('\n')[0].slice(0, 80) || 'Event',
      timestamp: now,
      onClick: onGoToEvents,
    }));

    return [...msgEvents, ...evtEvents];
  }, [messagesQuery.data, eventsQuery.data, onGoToMessages, onGoToEvents]);

  const isLoading = messagesQuery.isLoading || eventsQuery.isLoading;

  return (
    <div
      className="flex flex-col h-full overflow-hidden shrink-0"
      style={{ width: 320, background: 'rgb(var(--canvas-surface))', borderLeft: '1px solid rgb(var(--canvas-border))' }}
    >
      {/* Header */}
      <div
        className="flex flex-col items-center gap-3 shrink-0"
        style={{ padding: '20px 16px', borderBottom: '1px solid rgb(var(--canvas-border))' }}
      >
        <Avatar name={name} size="lg" />
        <div className="flex flex-col items-center gap-1 w-full text-center">
          <span className="text-lg font-bold" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
            {name}
          </span>
          {roleLabel && (
            <span className="text-[13px]" style={{ color: peopleColor }}>
              {roleLabel}
            </span>
          )}
        </div>
        <div
          className="flex items-center"
          style={{ background: getDomainColorWithAlpha('people', '20'), borderRadius: 10, padding: '3px 8px' }}
        >
          <span className="text-[10px]" style={{ color: peopleColor }}>{label}</span>
        </div>
      </div>

      {/* Interactions */}
      <div className="flex flex-col shrink-0 px-4 pt-4 pb-1">
        <span className="text-[10px] font-bold tracking-wider" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          RECENT INTERACTIONS
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {isLoading ? (
          <div className="space-y-2 px-2 pt-2">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="animate-pulse rounded-lg h-12" style={{ background: 'rgb(var(--canvas-border))' }} />
            ))}
          </div>
        ) : (
          <ActivityTimeline
            events={timelineEvents}
            emptyState="No recent interactions found"
          />
        )}
      </div>
    </div>
  );
}

// ── Empty detail ───────────────────────────────────────────────────

function EmptyDetail(): ReactNode {
  return (
    <div
      className="flex flex-col items-center justify-center h-full shrink-0 gap-3"
      style={{ width: 320, background: 'rgb(var(--canvas-surface))', borderLeft: '1px solid rgb(var(--canvas-border))' }}
    >
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 48, height: 48, background: getDomainColorWithAlpha('people', '20') }}
      >
        <UsersIcon className="w-6 h-6" style={{ color: peopleColor }} />
      </div>
      <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
        Select a contact to view details
      </p>
    </div>
  );
}

// ── Relationship Graph Panel ───────────────────────────────────────

function RelationshipGraphPanel({
  source,
  allSources,
}: {
  source: SourceSummary;
  allSources: SourceSummary[];
}): ReactNode {
  const name = source.display_name ?? source.origin_ref;
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string | undefined>(source.source_id);

  const { data: chunksData, isLoading: isChunksLoading } = useQuery({
    queryKey: ['source-chunks-people', source.source_id],
    queryFn: () => fetchSourceChunks(source.source_id, undefined, 1, 0),
    staleTime: 60_000,
  });

  const meta = useMemo((): PeopleMeta | null => {
    const firstChunk = chunksData?.chunks?.[0];
    return firstChunk ? extractPeopleMeta(firstChunk.domain_metadata) : null;
  }, [chunksData]);

  const orgQuery = useQuery({
    queryKey: ['graph-org-search', meta?.organization],
    queryFn: () =>
      postQuery({
        query: meta!.organization!,
        top_k: 8,
        domain_filter: 'people',
        source_filter: null,
        rerank: false,
      }),
    enabled: !!meta?.organization,
    staleTime: 60_000,
  });

  const { nodes, edges } = useMemo((): { nodes: GraphNodeData[]; edges: GraphEdgeData[] } => {
    const graphNodes: GraphNodeData[] = [
      { id: source.source_id, label: name, kind: 'person', domainColor: 'people' },
    ];
    const graphEdges: GraphEdgeData[] = [];

    if (orgQuery.data?.results) {
      const seenIds = new Set<string>([source.source_id]);
      for (const result of orgQuery.data.results) {
        if (seenIds.has(result.source_id)) continue;
        const peer = allSources.find(s => s.source_id === result.source_id);
        if (!peer) continue;
        seenIds.add(result.source_id);
        graphNodes.push({
          id: peer.source_id,
          label: peer.display_name ?? peer.origin_ref,
          kind: 'person',
          domainColor: 'people',
        });
        graphEdges.push({
          id: `edge-${source.source_id}-${peer.source_id}`,
          sourceId: source.source_id,
          targetId: peer.source_id,
          label: 'colleague',
        });
      }
    }

    return { nodes: graphNodes, edges: graphEdges };
  }, [source.source_id, name, orgQuery.data, allSources]);

  const renderNode = useCallback(
    (node: GraphNodeData, selected: boolean) => (
      <GraphNode
        id={node.id}
        label={node.label}
        kind={node.kind}
        domainColor={node.domainColor}
        selected={selected}
        onSelect={setSelectedGraphNodeId}
      />
    ),
    [setSelectedGraphNodeId],
  );

  const isLoading = isChunksLoading || (!!meta?.organization && orgQuery.isLoading);
  const hasConnections = nodes.length > 1;

  return (
    <div
      className="flex flex-col h-full overflow-hidden shrink-0"
      style={{
        width: 320,
        background: 'rgb(var(--canvas-bg))',
        borderLeft: '1px solid rgb(var(--canvas-border))',
      }}
    >
      <div
        className="flex items-center shrink-0 px-4"
        style={{
          height: 44,
          borderBottom: '1px solid rgb(var(--canvas-border))',
          background: 'rgb(var(--canvas-surface))',
        }}
      >
        <span className="text-[10px] font-bold tracking-wider" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          CONNECTIONS
        </span>
      </div>

      <div className="flex-1 min-h-0">
        {isLoading ? (
          <div className="flex flex-wrap gap-2 p-4">
            {[1, 2, 3].map(i => (
              <div
                key={i}
                className="animate-pulse rounded-full"
                style={{ width: 64, height: 64, background: 'rgb(var(--canvas-border))' }}
              />
            ))}
          </div>
        ) : !hasConnections ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 px-4">
            <p className="text-sm text-center" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              No connections found
            </p>
          </div>
        ) : (
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            layout="force"
            selectedNodeId={selectedGraphNodeId}
            onNodeSelect={setSelectedGraphNodeId}
            renderNode={renderNode}
            style={{ height: '100%' }}
          />
        )}
      </div>
    </div>
  );
}

// ── PeoplePage ─────────────────────────────────────────────────────

export default function PeoplePage(): ReactNode {
  const navigate = useNavigate();
  const { contact_id: selectedContactId } = useSearch({ from: '/people' });
  const [filterText, setFilterText] = useState('');
  const [alphaFilter, setAlphaFilter] = useState<string | undefined>(undefined);
  const [adapterFilter, setAdapterFilter] = useState<string[]>([]);

  const sourcesQuery = useSources({ domain: 'people', limit: 500 });
  const sources = sourcesQuery.data?.sources ?? EMPTY_SOURCES;

  const uniqueAdapters = useMemo(() => {
    const seen = new Set<string>();
    const result: Array<{ id: string; label: string }> = [];
    for (const s of sources) {
      if (!seen.has(s.adapter_id)) {
        seen.add(s.adapter_id);
        result.push({ id: s.adapter_id, label: adapterLabel(s.adapter_id) });
      }
    }
    return result.sort((a, b) => a.label.localeCompare(b.label));
  }, [sources]);

  const availableLetters = useMemo((): Set<string> => {
    const letters = new Set<string>();
    for (const s of sources) {
      const name = (s.display_name ?? s.origin_ref).trim();
      if (name) letters.add(name[0].toUpperCase());
    }
    return letters;
  }, [sources]);

  const filteredSources = useMemo(() => {
    let list = sources;

    if (adapterFilter.length > 0) {
      list = list.filter(s => adapterFilter.includes(s.adapter_id));
    }

    if (alphaFilter) {
      list = list.filter(s => {
        const name = (s.display_name ?? s.origin_ref).trim();
        return name[0]?.toUpperCase() === alphaFilter;
      });
    }

    if (filterText.trim()) {
      const q = filterText.toLowerCase();
      list = list.filter(s => {
        const name = (s.display_name ?? s.origin_ref).toLowerCase();
        return name.includes(q);
      });
    }

    return [...list].sort((a, b) => {
      const na = (a.display_name ?? a.origin_ref).toLowerCase();
      const nb = (b.display_name ?? b.origin_ref).toLowerCase();
      return na.localeCompare(nb);
    });
  }, [sources, filterText, alphaFilter, adapterFilter]);

  const selectedSource = useMemo(
    () => (selectedContactId ? sources.find(s => s.source_id === selectedContactId) ?? null : null),
    [sources, selectedContactId],
  );

  function selectContact(sourceId: string): void {
    const next = sourceId === selectedContactId ? undefined : sourceId;
    void navigate({ to: '/people', search: next ? { contact_id: next } : {} });
  }

  function handleLetterClick(letter: string): void {
    setAlphaFilter(prev => (prev === letter ? undefined : letter));
  }

  function goToMessages(): void {
    void navigate({ to: '/messages', search: {} });
  }

  function goToEvents(): void {
    void navigate({ to: '/events', search: {} });
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Domains"
        title="People"
        subtitle="Contacts and their connections"
      />
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* ── Left panel: toolbar + alphabet + contact grid ── */}
        <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
          {/* Toolbar */}
          <div
            className="flex items-center gap-3 shrink-0 px-5"
            style={{ height: 52, background: 'rgb(var(--canvas-surface))', borderBottom: '1px solid rgb(var(--canvas-border))' }}
          >
            {/* Adapter filter */}
            {uniqueAdapters.length > 1 && (
              <FilterDropdown
                mode="checkbox"
                value={adapterFilter}
                onChange={setAdapterFilter}
              >
                <FilterDropdown.Trigger
                  label="Source"
                  summary={adapterFilter.length > 0 ? `${adapterFilter.length} source${adapterFilter.length > 1 ? 's' : ''}` : 'All sources'}
                />
                <FilterDropdown.Panel>
                  <FilterDropdown.Section title="Source">
                    {uniqueAdapters.map(a => (
                      <FilterDropdown.Checkbox key={a.id} value={a.id} label={a.label} />
                    ))}
                  </FilterDropdown.Section>
                </FilterDropdown.Panel>
              </FilterDropdown>
            )}

            <div className="flex-1" />

            {/* Search */}
            <div
              className="flex items-center gap-2"
              style={{
                width: 220,
                height: 34,
                background: 'rgb(var(--canvas-border))',
                border: '1px solid rgb(var(--canvas-border))',
                borderRadius: 6,
                padding: '0 12px',
              }}
            >
              <span style={{ color: 'rgb(var(--canvas-fg-3))', flexShrink: 0 }}>
                <Icon name="search" size={14} />
              </span>
              <input
                type="text"
                value={filterText}
                onChange={e => setFilterText(e.target.value)}
                placeholder="Search contacts…"
                className="flex-1 bg-transparent text-xs outline-none"
                style={{ color: 'rgb(var(--canvas-fg-1))', fontSize: 12 }}
              />
            </div>
          </div>

          {/* Alphabet index strip */}
          {sources.length > 0 && (
            <div style={{ borderBottom: '1px solid rgb(var(--canvas-border))', background: 'rgb(var(--canvas-surface))' }}>
              <AlphabetIndex
                available={availableLetters}
                active={alphaFilter}
                onLetterClick={handleLetterClick}
              />
            </div>
          )}

          {/* Contact grid */}
          <div className="flex-1 overflow-y-auto" style={{ padding: '12px 16px' }}>
            {sourcesQuery.isLoading ? (
              <div className="flex flex-wrap gap-3">
                {[1, 2, 3, 4, 5, 6].map(i => (
                  <div
                    key={i}
                    className="animate-pulse rounded-lg"
                    style={{ width: 192, height: 128, background: 'rgb(var(--canvas-surface))' }}
                  />
                ))}
              </div>
            ) : sourcesQuery.isError ? (
              <div
                className="rounded-lg p-4 text-sm"
                style={{ background: 'rgb(var(--status-error) / 0.13)', color: 'rgb(var(--canvas-fg-2))' }}
              >
                Failed to load contacts.
              </div>
            ) : filteredSources.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <div
                  className="flex items-center justify-center rounded-2xl"
                  style={{ width: 48, height: 48, background: getDomainColorWithAlpha('people', '20') }}
                >
                  <UsersIcon className="w-6 h-6" style={{ color: peopleColor }} />
                </div>
                <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  {filterText || alphaFilter || adapterFilter.length > 0
                    ? 'No contacts match your filters'
                    : 'No contacts ingested yet'}
                </p>
              </div>
            ) : (
              <div className="flex flex-wrap gap-3">
                {filteredSources.map(source => (
                  <ContactCard
                    key={source.source_id}
                    source={source}
                    isSelected={source.source_id === selectedContactId}
                    onClick={() => selectContact(source.source_id)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Count footer */}
          {!sourcesQuery.isLoading && filteredSources.length > 0 && (
            <div
              className="shrink-0 px-5 py-2"
              style={{ borderTop: `1px solid rgb(var(--canvas-border))` }}
            >
              <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                {filteredSources.length}{' '}
                {filteredSources.length === 1 ? 'contact' : 'contacts'}
                {filterText && ` matching "${filterText}"`}
              </span>
            </div>
          )}
        </div>

        {/* ── Right panels: detail + relationship graph, or empty state ── */}
        {selectedSource ? (
          <>
            <DetailPanel
              source={selectedSource}
              onGoToMessages={goToMessages}
              onGoToEvents={goToEvents}
            />
            <RelationshipGraphPanel
              key={selectedSource.source_id}
              source={selectedSource}
              allSources={sources}
            />
          </>
        ) : (
          <EmptyDetail />
        )}
      </div>
    </div>
  );
}
