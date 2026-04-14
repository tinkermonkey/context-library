import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState, useRef, useEffect } from 'react';
import type { ReactNode } from 'react';
import { MagnifyingGlassIcon, ChatBubbleLeftIcon, LockClosedIcon } from '@heroicons/react/24/outline';
import { useSources } from '../hooks/useSources';
import { fetchSourceChunks } from '../api/client';
import { colors, getDomainColor } from '../lib/designTokens';
import type { SourceSummary, ChunkResponse } from '../types/api';

const msgColor = getDomainColor('messages'); // #A855F7

// ── Types ──────────────────────────────────────────────────────────

/**
 * Mirrors backend MessageMetadata exactly (storage/models.py).
 * All fields must stay in sync with the Pydantic model.
 */
interface MessageMeta {
  thread_id: string;
  message_id: string;
  sender: string;
  recipients: string[];
  timestamp: string;
  is_from_me: boolean;
  subject: string | null;
  in_reply_to: string | null;
  is_thread_root: boolean;
}

function extractMessageMeta(chunk: ChunkResponse): MessageMeta | null {
  const dm = chunk.domain_metadata;
  if (!dm) return null;
  return {
    thread_id: typeof dm.thread_id === 'string' ? dm.thread_id : '',
    message_id: typeof dm.message_id === 'string' ? dm.message_id : '',
    sender: typeof dm.sender === 'string' ? dm.sender : 'Unknown',
    recipients: Array.isArray(dm.recipients) ? (dm.recipients as string[]) : [],
    timestamp: typeof dm.timestamp === 'string' ? dm.timestamp : '',
    is_from_me: typeof dm.is_from_me === 'boolean' ? dm.is_from_me : false,
    subject: typeof dm.subject === 'string' ? dm.subject : null,
    in_reply_to: typeof dm.in_reply_to === 'string' ? dm.in_reply_to : null,
    is_thread_root: typeof dm.is_thread_root === 'boolean' ? dm.is_thread_root : false,
  };
}

// ── Helpers ────────────────────────────────────────────────────────

function formatTimeAgo(iso: string): string {
  if (!iso) return '';
  const now = Date.now();
  const then = new Date(iso).getTime();
  if (isNaN(then)) return '';
  const diff = now - then;
  const mins = Math.floor(diff / 60_000);
  if (mins < 2) return 'just now';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days}d`;
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatMessageTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

function formatDividerTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function getInitials(name: string): string {
  const clean = name.replace(/[<>()[\]]/g, '').trim();
  if (!clean) return '?';
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return clean.slice(0, 2).toUpperCase();
}

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

function conversationName(source: SourceSummary): string {
  if (source.display_name) return source.display_name;
  const ref = source.origin_ref;
  const colon = ref.indexOf(':');
  // Strip the scheme prefix (e.g. "imessage:+15551234567" → "+15551234567")
  const after = colon >= 0 ? ref.slice(colon + 1).trim() : '';
  return after || ref;
}

// ── Avatar ─────────────────────────────────────────────────────────

function Avatar({ name, size = 36 }: { name: string; size?: number }): ReactNode {
  const bg = avatarColor(name);
  return (
    <div
      className="rounded-full shrink-0 flex items-center justify-center font-semibold select-none"
      style={{
        width: size, height: size,
        background: `${bg}30`,
        color: bg,
        fontSize: Math.floor(size * 0.38),
      }}
    >
      {getInitials(name)}
    </div>
  );
}

// ── ConversationItem ───────────────────────────────────────────────

function ConversationItem({
  source,
  isSelected,
  onClick,
}: {
  source: SourceSummary;
  isSelected: boolean;
  onClick: () => void;
}): ReactNode {
  const name = conversationName(source);
  const ref = useRef<HTMLButtonElement>(null);

  // Keep selected item visible in the scrollable list
  useEffect(() => {
    if (isSelected && ref.current) {
      ref.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [isSelected]);

  return (
    <button
      ref={ref}
      onClick={onClick}
      className="w-full text-left px-3 py-2.5 flex items-center gap-2.5 transition-colors"
      style={{
        background: isSelected ? `${msgColor}18` : 'transparent',
        borderLeft: `2px solid ${isSelected ? msgColor : 'transparent'}`,
      }}
    >
      <Avatar name={name} size={36} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-1 mb-0.5">
          <span
            className="text-sm font-medium truncate"
            style={{ color: isSelected ? colors.textPrimary : colors.textMuted }}
          >
            {name}
          </span>
          <span className="text-xs shrink-0" style={{ color: colors.textDim }}>
            {formatTimeAgo(source.updated_at)}
          </span>
        </div>
        <div className="text-xs" style={{ color: colors.textDim }}>
          {source.chunk_count} {source.chunk_count === 1 ? 'message' : 'messages'}
        </div>
      </div>
    </button>
  );
}

// ── TimestampDivider ───────────────────────────────────────────────

function TimestampDivider({ timestamp }: { timestamp: string }): ReactNode {
  return (
    <div className="flex items-center gap-3 my-3 px-4">
      <div className="flex-1 h-px" style={{ background: colors.borderSubtle }} />
      <span className="text-xs shrink-0" style={{ color: colors.textDim }}>
        {formatDividerTime(timestamp)}
      </span>
      <div className="flex-1 h-px" style={{ background: colors.borderSubtle }} />
    </div>
  );
}

// ── MessageBubble ─────────────────────────────────────────────────

function MessageBubble({
  chunk,
  meta,
  showSender,
}: {
  chunk: ChunkResponse;
  meta: MessageMeta;
  showSender: boolean;
}): ReactNode {
  const fromMe = meta.is_from_me;
  const timeStr = formatMessageTime(meta.timestamp);

  return (
    <div className={`flex flex-col mb-0.5 px-4 ${fromMe ? 'items-end' : 'items-start'}`}>
      {showSender && !fromMe && (
        <span className="text-xs mb-1 ml-1" style={{ color: colors.textDim }}>
          {meta.sender}
        </span>
      )}
      <div
        className="max-w-[70%] rounded-2xl px-3.5 py-2"
        style={
          fromMe
            ? {
                background: `linear-gradient(135deg, ${msgColor}CC 0%, ${msgColor}88 100%)`,
                borderBottomRightRadius: 4,
              }
            : {
                background: colors.bgElevated,
                borderBottomLeftRadius: 4,
              }
        }
      >
        <p
          className="text-sm leading-relaxed whitespace-pre-wrap break-words overflow-x-hidden"
          style={{ color: fromMe ? '#F9FAFB' : colors.textMuted }}
        >
          {chunk.content}
        </p>
      </div>
      <span className="text-xs mt-0.5 mx-1" style={{ color: colors.textDim }}>
        {timeStr}
      </span>
    </div>
  );
}

// ── MessageThread ─────────────────────────────────────────────────

/**
 * Messages are an immutable archive — we page backwards from the end.
 * Initial load: offset = max(0, chunk_count - PAGE_SIZE) → most recent batch.
 * "Load earlier" decrements startOffset by PAGE_SIZE toward 0.
 * The API returns chunks in chunk_index order (ascending by ingestion).
 * We sort the accumulated chunks by domain_metadata.timestamp before display.
 */
const PAGE_SIZE = 50;

type DisplayItem =
  | { kind: 'divider'; timestamp: string; key: string }
  | { kind: 'message'; chunk: ChunkResponse; meta: MessageMeta; showSender: boolean; key: string };

function MessageThread({ source }: { source: SourceSummary }): ReactNode {
  const bottomRef = useRef<HTMLDivElement>(null);
  const hasScrolledToBottom = useRef(false);
  const name = conversationName(source);

  // Start at the most recent page (end of the chunk list).
  const [startOffset, setStartOffset] = useState(() =>
    Math.max(0, source.chunk_count - PAGE_SIZE),
  );
  const [loaded, setLoaded] = useState<ChunkResponse[]>([]);

  // Reset everything when the conversation changes.
  useEffect(() => {
    hasScrolledToBottom.current = false;
    setStartOffset(Math.max(0, source.chunk_count - PAGE_SIZE));
    setLoaded([]);
  }, [source.source_id, source.chunk_count]);

  // Fetch the current page. Archives are immutable → staleTime: Infinity.
  const { data, isLoading } = useQuery({
    queryKey: ['chunks', source.source_id, startOffset],
    queryFn: () => fetchSourceChunks(source.source_id, undefined, PAGE_SIZE, startOffset),
    staleTime: Infinity,
  });

  // Accumulate pages. Guard against stale data from a previous conversation
  // by comparing data.source_id to the currently selected source.
  useEffect(() => {
    if (!data?.chunks || data.source_id !== source.source_id) return;
    setLoaded(prev => {
      const seen = new Set(prev.map(c => c.chunk_hash));
      const fresh = data.chunks.filter(c => !seen.has(c.chunk_hash));
      if (fresh.length === 0) return prev;
      // Prepend: earlier pages (lower offset) contain older messages.
      return [...fresh, ...prev];
    });
  }, [data, source.source_id]);

  // Scroll to the bottom after the initial load. Deferred to next paint so
  // the message list has committed to the DOM before we measure.
  useEffect(() => {
    if (!isLoading && loaded.length > 0 && !hasScrolledToBottom.current) {
      const timer = setTimeout(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'instant' });
        hasScrolledToBottom.current = true;
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [isLoading, loaded.length]);

  // "Load earlier" is available while there are chunks before our current window.
  const hasEarlier = startOffset > 0;
  const isPaginating = isLoading && loaded.length > 0;

  function loadEarlier(): void {
    setStartOffset(prev => Math.max(0, prev - PAGE_SIZE));
  }

  // Sort by ISO timestamp string (lexicographic == chronological for ISO 8601)
  // then build display items with time-gap dividers.
  const items = useMemo((): DisplayItem[] => {
    const sorted = [...loaded].sort((a, b) => {
      const ta = typeof a.domain_metadata?.timestamp === 'string'
        ? a.domain_metadata.timestamp
        : '';
      const tb = typeof b.domain_metadata?.timestamp === 'string'
        ? b.domain_metadata.timestamp
        : '';
      return ta.localeCompare(tb);
    });

    const result: DisplayItem[] = [];
    let lastTs: Date | null = null;
    let lastSender: string | null = null;

    for (const chunk of sorted) {
      const meta = extractMessageMeta(chunk);
      if (!meta) continue; // chunk missing domain_metadata — skip silently

      const msgDate = new Date(meta.timestamp);
      const valid = !isNaN(msgDate.getTime());

      if (valid) {
        if (!lastTs) {
          // Always show a divider before the first message
          result.push({ kind: 'divider', timestamp: meta.timestamp, key: `div-first-${chunk.chunk_hash}` });
        } else if (msgDate.getTime() - lastTs.getTime() > 60 * 60 * 1_000) {
          // Show a divider when there is a gap of more than one hour
          result.push({ kind: 'divider', timestamp: meta.timestamp, key: `div-${chunk.chunk_hash}` });
        }
        lastTs = msgDate;
      }

      // Show sender label at the start of a run of inbound messages from the same person
      const showSender = !meta.is_from_me && meta.sender !== lastSender;
      result.push({ kind: 'message', chunk, meta, showSender, key: chunk.chunk_hash });
      lastSender = meta.sender;
    }
    return result;
  }, [loaded]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Thread header */}
      <div
        className="px-5 py-3 shrink-0 flex items-center gap-3"
        style={{ borderBottom: `1px solid ${colors.border}`, background: colors.bgSurface }}
      >
        <Avatar name={name} size={32} />
        <div>
          <div className="text-sm font-semibold" style={{ color: colors.textPrimary }}>{name}</div>
          <div className="text-xs" style={{ color: colors.textDim }}>
            {source.chunk_count} {source.chunk_count === 1 ? 'message' : 'messages'}
          </div>
        </div>
      </div>

      {/* Scrollable messages */}
      <div className="flex-1 overflow-y-auto py-2" style={{ background: colors.bgBase }}>
        {/* Load-earlier button or spinner */}
        {hasEarlier && (
          <div className="flex justify-center py-3">
            {isPaginating ? (
              <div
                className="w-4 h-4 rounded-full border-2 animate-spin"
                style={{ borderColor: `${colors.textDim} transparent transparent transparent` }}
              />
            ) : (
              <button
                onClick={loadEarlier}
                className="px-4 py-1.5 rounded-full text-xs font-medium transition-opacity hover:opacity-75"
                style={{
                  background: colors.bgElevated,
                  color: colors.textMuted,
                  border: `1px solid ${colors.border}`,
                }}
              >
                Load earlier messages
              </button>
            )}
          </div>
        )}

        {/* Initial loading skeleton */}
        {isLoading && loaded.length === 0 && (
          <div className="px-4 py-4 space-y-4">
            {[40, 65, 50, 30, 60].map((w, i) => (
              <div key={i} className={`flex ${i % 2 ? 'justify-end' : 'justify-start'}`}>
                <div
                  className="h-9 rounded-2xl animate-pulse"
                  style={{ width: `${w}%`, background: colors.bgElevated }}
                />
              </div>
            ))}
          </div>
        )}

        {/* Message items */}
        {items.map(item =>
          item.kind === 'divider' ? (
            <TimestampDivider key={item.key} timestamp={item.timestamp} />
          ) : (
            <MessageBubble
              key={item.key}
              chunk={item.chunk}
              meta={item.meta}
              showSender={item.showSender}
            />
          )
        )}

        {!isLoading && loaded.length === 0 && (
          <div className="flex items-center justify-center h-32">
            <p className="text-sm" style={{ color: colors.textDim }}>No messages found.</p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Read-only archive banner */}
      <div
        className="shrink-0 flex items-center justify-center gap-2 py-2 px-4"
        style={{ borderTop: `1px solid ${colors.border}`, background: colors.bgSurface }}
      >
        <LockClosedIcon className="w-3.5 h-3.5 shrink-0" style={{ color: colors.textMuted }} />
        <span className="text-xs" style={{ color: colors.textMuted }}>
          Archive — read only. This is historical data, not a live messenger.
        </span>
      </div>
    </div>
  );
}

// ── EmptyState ────────────────────────────────────────────────────

function EmptyState(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 48, height: 48, background: `${msgColor}20` }}
      >
        <ChatBubbleLeftIcon className="w-6 h-6" style={{ color: msgColor }} />
      </div>
      <p className="text-sm" style={{ color: colors.textDim }}>
        Select a conversation to view messages
      </p>
    </div>
  );
}

// ── MessagesPage ──────────────────────────────────────────────────

export default function MessagesPage(): ReactNode {
  const navigate = useNavigate();
  const { thread_id: selectedThreadId } = useSearch({ from: '/messages' });
  const [filterText, setFilterText] = useState('');

  const sourcesQuery = useSources({ domain: 'messages', limit: 500 });
  const sources = sourcesQuery.data?.sources ?? [];

  // Filter by contact name / origin_ref, sort by most recent
  const filteredSources = useMemo(() => {
    let list = sources;
    if (filterText.trim()) {
      const q = filterText.toLowerCase();
      list = list.filter(s => {
        const name = conversationName(s).toLowerCase();
        return name.includes(q) || s.origin_ref.toLowerCase().includes(q);
      });
    }
    return [...list].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
  }, [sources, filterText]);

  const selectedSource = useMemo(
    () => sources.find(s => s.source_id === selectedThreadId) ?? null,
    [sources, selectedThreadId],
  );

  function selectThread(sourceId: string): void {
    void navigate({ to: '/messages', search: { thread_id: sourceId } });
  }

  return (
    <div className="flex h-full overflow-hidden" style={{ background: colors.bgBase }}>
      {/* ── Left panel: conversation list ── */}
      <div
        className="w-72 shrink-0 flex flex-col overflow-hidden"
        style={{ borderRight: `1px solid ${colors.border}`, background: colors.bgSurface }}
      >
        {/* Search bar */}
        <div
          className="px-3 py-2.5 shrink-0"
          style={{ borderBottom: `1px solid ${colors.border}` }}
        >
          <div
            className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg"
            style={{ background: colors.bgElevated }}
          >
            <MagnifyingGlassIcon
              className="w-3.5 h-3.5 shrink-0"
              style={{ color: colors.textDim }}
            />
            <input
              type="text"
              value={filterText}
              onChange={e => setFilterText(e.target.value)}
              placeholder="Search conversations…"
              className="flex-1 bg-transparent text-xs outline-none"
              style={{ color: colors.textPrimary }}
            />
          </div>
        </div>

        {/* Count row */}
        <div className="px-4 py-1.5 shrink-0">
          <span className="text-xs" style={{ color: colors.textDim }}>
            {filteredSources.length}{' '}
            {filteredSources.length === 1 ? 'conversation' : 'conversations'}
          </span>
        </div>

        {/* Scrollable conversation list */}
        <div className="flex-1 overflow-y-auto">
          {sourcesQuery.isLoading ? (
            <div className="px-3 py-2 space-y-3">
              {[1, 2, 3, 4, 5].map(i => (
                <div key={i} className="flex items-center gap-2.5 animate-pulse">
                  <div
                    className="rounded-full shrink-0"
                    style={{ width: 36, height: 36, background: colors.bgElevated }}
                  />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-3 rounded" style={{ width: '60%', background: colors.bgElevated }} />
                    <div className="h-2.5 rounded" style={{ width: '80%', background: colors.bgElevated }} />
                  </div>
                </div>
              ))}
            </div>
          ) : filteredSources.length === 0 ? (
            <div className="px-4 py-6 text-center">
              <p className="text-xs" style={{ color: colors.textDim }}>
                {filterText ? 'No conversations match your search' : 'No conversations found'}
              </p>
            </div>
          ) : (
            filteredSources.map(source => (
              <ConversationItem
                key={source.source_id}
                source={source}
                isSelected={source.source_id === selectedThreadId}
                onClick={() => selectThread(source.source_id)}
              />
            ))
          )}
        </div>
      </div>

      {/* ── Right panel: thread view ── */}
      <div className="flex-1 min-w-0 overflow-hidden">
        {selectedSource ? <MessageThread source={selectedSource} /> : <EmptyState />}
      </div>
    </div>
  );
}
