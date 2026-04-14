import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { MagnifyingGlassIcon, UsersIcon } from '@heroicons/react/24/outline';
import { useSources } from '../hooks/useSources';
import { postQuery, fetchSourceChunks } from '../api/client';
import { colors, getDomainColor } from '../lib/designTokens';
import type { SourceSummary, QueryResultItem } from '../types/api';

const peopleColor = getDomainColor('people'); // #EC4899
const msgColor = getDomainColor('messages');
const evtColor = getDomainColor('events');

// ── Avatar helpers ─────────────────────────────────────────────────

const AVATAR_PALETTE = [
  '#6366F1', '#A855F7', '#EC4899', '#F43F5E',
  '#F97316', '#F59E0B', '#22C55E', '#14B8A6',
  '#06B6D4', '#3B82F6',
];

function avatarColor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0x7fffffff;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function getInitials(name: string): string {
  const clean = name.replace(/[<>()[\]]/g, '').trim();
  if (!clean) return '?';
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return clean.slice(0, 2).toUpperCase();
}

function Avatar({ name, size = 44 }: { name: string; size?: number }): ReactNode {
  const bg = avatarColor(name);
  return (
    <div
      className="rounded-full shrink-0 flex items-center justify-center font-semibold select-none"
      style={{
        width: size,
        height: size,
        background: `${bg}30`,
        color: bg,
        fontSize: Math.floor(size * 0.38),
      }}
    >
      {getInitials(name)}
    </div>
  );
}

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
        background: isSelected ? `${peopleColor}18` : '#161616',
        border: `1px solid ${isSelected ? peopleColor : '#1E1E1E'}`,
        borderRadius: 8,
        flexShrink: 0,
      }}
    >
      <Avatar name={name} size={44} />
      <div className="flex flex-col gap-0.5 min-w-0 w-full">
        <span
          className="text-sm font-semibold truncate"
          style={{ color: colors.textPrimary }}
        >
          {name}
        </span>
      </div>
      <div
        className="flex items-center self-start"
        style={{ background: '#1F2937', borderRadius: 4, padding: '3px 8px' }}
      >
        <span className="text-[10px]" style={{ color: '#6B7280' }}>{label}</span>
      </div>
    </button>
  );
}

// ── Related Messages ───────────────────────────────────────────────

function RelatedMessages({
  sourceId,
  contactName,
  onGoToMessages,
}: {
  sourceId: string;
  contactName: string;
  onGoToMessages: () => void;
}): ReactNode {
  // sourceId in the query key prevents cache collision between contacts with the same name
  const { data, isLoading, isError } = useQuery({
    queryKey: ['people-messages', sourceId, contactName],
    queryFn: () =>
      postQuery({
        query: contactName,
        top_k: 5,
        domain_filter: 'messages',
        source_filter: null,
        rerank: false,
      }),
    enabled: !!contactName,
    staleTime: 60_000,
  });

  const items = data?.results ?? [];

  return (
    <div className="flex flex-col gap-2 w-full">
      <span className="text-[10px] font-bold tracking-wider" style={{ color: '#4B5563' }}>
        RECENT INTERACTIONS
      </span>

      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="animate-pulse rounded-lg h-14" style={{ background: '#1A1A1A' }} />
          ))}
        </div>
      )}

      {!isLoading && isError && (
        <div className="rounded-lg px-3 py-2 text-xs" style={{ background: '#1A1A1A', color: colors.statusRed }}>
          Failed to load messages
        </div>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <div className="rounded-lg px-3 py-2 text-xs" style={{ background: '#1A1A1A', color: colors.textDim }}>
          No messages found
        </div>
      )}

      {!isLoading && !isError && items.map((item: QueryResultItem) => (
        <button
          key={item.chunk_hash}
          onClick={onGoToMessages}
          className="text-left flex flex-col gap-1 w-full transition-opacity hover:opacity-80"
          style={{ background: '#1A1A1A', padding: '10px 12px', borderRadius: 6 }}
        >
          <span className="text-[10px]" style={{ color: '#6B7280' }}>
            {item.adapter_id.replace(/:default$/, '').replace(/_/g, ' ')}
          </span>
          <span
            className="text-xs leading-relaxed line-clamp-2"
            style={{ color: '#D1D5DB', lineHeight: 1.5 }}
          >
            {item.chunk_text}
          </span>
        </button>
      ))}

      {!isLoading && !isError && items.length > 0 && (
        <button
          onClick={onGoToMessages}
          className="text-xs transition-opacity hover:opacity-75 self-start mt-1"
          style={{ color: msgColor }}
        >
          View all messages →
        </button>
      )}
    </div>
  );
}

// ── Related Events ─────────────────────────────────────────────────

function RelatedEvents({
  sourceId,
  contactName,
  onGoToEvents,
}: {
  sourceId: string;
  contactName: string;
  onGoToEvents: () => void;
}): ReactNode {
  // sourceId in the query key prevents cache collision between contacts with the same name
  const { data, isLoading, isError } = useQuery({
    queryKey: ['people-events', sourceId, contactName],
    queryFn: () =>
      postQuery({
        query: contactName,
        top_k: 3,
        domain_filter: 'events',
        source_filter: null,
        rerank: false,
      }),
    enabled: !!contactName,
    staleTime: 60_000,
  });

  const items = data?.results ?? [];

  return (
    <div className="flex flex-col gap-2 w-full">
      <span className="text-[10px] font-bold tracking-wider" style={{ color: '#4B5563' }}>
        RELATED EVENTS
      </span>

      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="animate-pulse rounded-lg h-10" style={{ background: '#1A1A1A' }} />
          ))}
        </div>
      )}

      {!isLoading && isError && (
        <div className="rounded-lg px-3 py-2 text-xs" style={{ background: '#1A1A1A', color: colors.statusRed }}>
          Failed to load events
        </div>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <div className="rounded-lg px-3 py-2 text-xs" style={{ background: '#1A1A1A', color: colors.textDim }}>
          No events found
        </div>
      )}

      {!isLoading && !isError && items.map((item: QueryResultItem) => (
        <button
          key={item.chunk_hash}
          onClick={onGoToEvents}
          className="text-left flex items-center gap-2.5 w-full transition-opacity hover:opacity-80"
          style={{ background: '#1A1A1A', padding: '8px 12px', borderRadius: 6 }}
        >
          <div className="rounded-full shrink-0" style={{ width: 8, height: 8, background: evtColor }} />
          <span className="text-xs flex-1 min-w-0 truncate" style={{ color: '#D1D5DB' }}>
            {item.chunk_text.split('\n')[0]}
          </span>
        </button>
      ))}

      {!isLoading && !isError && items.length > 0 && (
        <button
          onClick={onGoToEvents}
          className="text-xs transition-opacity hover:opacity-75 self-start mt-1"
          style={{ color: evtColor }}
        >
          View all events →
        </button>
      )}
    </div>
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

  // Fetch first chunk to get domain_metadata (job_title, organization, etc.)
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

  return (
    <div
      className="flex flex-col h-full overflow-hidden shrink-0"
      style={{ width: 320, background: '#111111', borderLeft: '1px solid #1A1A1A' }}
    >
      {/* Header */}
      <div
        className="flex flex-col items-center gap-3 shrink-0"
        style={{ padding: '20px 16px', borderBottom: '1px solid #1A1A1A' }}
      >
        <Avatar name={name} size={64} />
        <div className="flex flex-col items-center gap-1 w-full text-center">
          <span className="text-lg font-bold" style={{ color: colors.textPrimary }}>
            {name}
          </span>
          {roleLabel && (
            <span className="text-[13px]" style={{ color: '#A5B4FC' }}>
              {roleLabel}
            </span>
          )}
        </div>
        <div
          className="flex items-center"
          style={{ background: '#312E81', borderRadius: 10, padding: '3px 8px' }}
        >
          <span className="text-[10px]" style={{ color: '#818CF8' }}>{label}</span>
        </div>
      </div>

      {/* Body — scrollable sections */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-4" style={{ padding: 16 }}>
        <RelatedMessages
          sourceId={source.source_id}
          contactName={name}
          onGoToMessages={onGoToMessages}
        />
        <RelatedEvents
          sourceId={source.source_id}
          contactName={name}
          onGoToEvents={onGoToEvents}
        />
      </div>
    </div>
  );
}

// ── Empty detail ───────────────────────────────────────────────────

function EmptyDetail(): ReactNode {
  return (
    <div
      className="flex flex-col items-center justify-center h-full shrink-0 gap-3"
      style={{ width: 320, background: '#111111', borderLeft: '1px solid #1A1A1A' }}
    >
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 48, height: 48, background: `${peopleColor}20` }}
      >
        <UsersIcon className="w-6 h-6" style={{ color: peopleColor }} />
      </div>
      <p className="text-sm" style={{ color: colors.textDim }}>
        Select a contact to view details
      </p>
    </div>
  );
}

// ── PeoplePage ─────────────────────────────────────────────────────

export default function PeoplePage(): ReactNode {
  const navigate = useNavigate();
  // URL-persisted selection — bookmarkable, survives reload and back-navigation
  const { contact_id: selectedContactId } = useSearch({ from: '/people' });
  const [filterText, setFilterText] = useState('');

  const sourcesQuery = useSources({ domain: 'people', limit: 500 });
  const sources = sourcesQuery.data?.sources ?? [];

  // Filter and sort contacts alphabetically by name
  const filteredSources = useMemo(() => {
    let list = sources;
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
  }, [sources, filterText]);

  const selectedSource = useMemo(
    () => (selectedContactId ? sources.find(s => s.source_id === selectedContactId) ?? null : null),
    [sources, selectedContactId],
  );

  function selectContact(sourceId: string): void {
    // Toggle off if already selected
    const next = sourceId === selectedContactId ? undefined : sourceId;
    void navigate({ to: '/people', search: next ? { contact_id: next } : {} });
  }

  function goToMessages(): void {
    void navigate({ to: '/messages', search: {} });
  }

  function goToEvents(): void {
    void navigate({ to: '/events', search: {} });
  }

  return (
    <div className="flex h-full overflow-hidden" style={{ background: colors.bgBase }}>
      {/* ── Left panel: search + contact grid ── */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {/* Top bar */}
        <div
          className="flex items-center gap-3 shrink-0 px-5"
          style={{ height: 52, background: '#111111', borderBottom: '1px solid #1A1A1A' }}
        >
          <span className="font-semibold flex-1" style={{ fontSize: 16, color: colors.textPrimary }}>
            People
          </span>
          <div
            className="flex items-center gap-2"
            style={{
              width: 240,
              height: 34,
              background: '#1A1A1A',
              border: '1px solid #2D2D2D',
              borderRadius: 6,
              padding: '0 12px',
            }}
          >
            <MagnifyingGlassIcon className="w-3.5 h-3.5 shrink-0" style={{ color: '#4B5563' }} />
            <input
              type="text"
              value={filterText}
              onChange={e => setFilterText(e.target.value)}
              placeholder="Search contacts…"
              className="flex-1 bg-transparent text-xs outline-none"
              style={{ color: colors.textPrimary, fontSize: 12 }}
            />
          </div>
        </div>

        {/* Contact grid */}
        <div className="flex-1 overflow-y-auto" style={{ padding: '12px 16px' }}>
          {sourcesQuery.isLoading ? (
            <div className="flex flex-wrap gap-3">
              {[1, 2, 3, 4, 5, 6].map(i => (
                <div
                  key={i}
                  className="animate-pulse rounded-lg"
                  style={{ width: 192, height: 128, background: '#161616' }}
                />
              ))}
            </div>
          ) : sourcesQuery.isError ? (
            <div
              className="rounded-lg p-4 text-sm"
              style={{ background: '#1F1010', color: colors.textMuted }}
            >
              Failed to load contacts.
            </div>
          ) : filteredSources.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <div
                className="flex items-center justify-center rounded-2xl"
                style={{ width: 48, height: 48, background: `${peopleColor}20` }}
              >
                <UsersIcon className="w-6 h-6" style={{ color: peopleColor }} />
              </div>
              <p className="text-sm" style={{ color: colors.textDim }}>
                {filterText ? 'No contacts match your search' : 'No contacts ingested yet'}
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
            style={{ borderTop: `1px solid ${colors.border}` }}
          >
            <span className="text-xs" style={{ color: colors.textDim }}>
              {filteredSources.length}{' '}
              {filteredSources.length === 1 ? 'contact' : 'contacts'}
              {filterText && ` matching "${filterText}"`}
            </span>
          </div>
        )}
      </div>

      {/* ── Right panel: detail or empty state ── */}
      {selectedSource ? (
        <DetailPanel
          source={selectedSource}
          onGoToMessages={goToMessages}
          onGoToEvents={goToEvents}
        />
      ) : (
        <EmptyDetail />
      )}
    </div>
  );
}
