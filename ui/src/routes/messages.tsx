import { useNavigate, useSearch } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, useRef, useEffect, useReducer } from "react";
import type { ReactNode } from "react";
import {
  ChatBubbleLeftIcon,
} from "@heroicons/react/24/outline";
import { SplitPane, Icon, PageHeader, ChatMessage } from "@tinkermonkey/heimdall-ui";
import { KVGrid } from "../components/KVGrid";
import { FilterDropdown } from "../components/FilterDropdown";
import { useSources } from "../hooks/useSources";
import { fetchSourceChunks } from "../api/client";
import { getDomainColor, getDomainColorWithAlpha } from "../lib/designTokens";
import type { SourceSummary, ChunkResponse } from "../types/api";

const msgColor = getDomainColor("messages");

// ── Types ──────────────────────────────────────────────────────────

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
    thread_id:     typeof dm.thread_id === "string" ? dm.thread_id : "",
    message_id:    typeof dm.message_id === "string" ? dm.message_id : "",
    sender:        typeof dm.sender === "string" ? dm.sender : "Unknown",
    recipients:    Array.isArray(dm.recipients) ? (dm.recipients as string[]) : [],
    timestamp:     typeof dm.timestamp === "string" ? dm.timestamp : "",
    is_from_me:    typeof dm.is_from_me === "boolean" ? dm.is_from_me : false,
    subject:       typeof dm.subject === "string" ? dm.subject : null,
    in_reply_to:   typeof dm.in_reply_to === "string" ? dm.in_reply_to : null,
    is_thread_root: typeof dm.is_thread_root === "boolean" ? dm.is_thread_root : false,
  };
}

// ── Helpers ────────────────────────────────────────────────────────

function formatTimeAgo(iso: string): string {
  if (!iso) return "";
  const now = Date.now();
  const then = new Date(iso).getTime();
  if (isNaN(then)) return "";
  const diff = now - then;
  const mins = Math.floor(diff / 60_000);
  if (mins < 2) return "just now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d`;
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function formatMessageTimestamp(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function formatDateRange(from: string, to: string): string {
  const f = new Date(from);
  const t = new Date(to);
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' };
  if (f.getFullYear() === t.getFullYear() && f.getMonth() === t.getMonth() && f.getDate() === t.getDate()) {
    return f.toLocaleDateString('en-US', opts);
  }
  return `${f.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} – ${t.toLocaleDateString('en-US', opts)}`;
}

function getInitials(name: string): string {
  const clean = name.replace(/[<>()[\]]/g, "").trim();
  if (!clean) return "?";
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length >= 2)
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return clean.slice(0, 2).toUpperCase();
}

const AVATAR_PALETTE = [
  "#6366F1", "#A855F7", "#EC4899", "#F43F5E", "#F97316",
  "#F59E0B", "#22C55E", "#14B8A6", "#06B6D4", "#3B82F6",
];

function avatarColor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++)
    h = (h * 31 + name.charCodeAt(i)) & 0x7fffffff;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function conversationName(source: SourceSummary): string {
  if (source.display_name) return source.display_name;
  const ref = source.origin_ref;
  const colon = ref.indexOf(":");
  const after = colon >= 0 ? ref.slice(colon + 1).trim() : "";
  return after || ref;
}

function adapterLabel(adapterId: string): string {
  const base = adapterId.split(':')[0];
  return base.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/** Remove quoted reply content (lines starting with >) from message text. */
function stripQuotedReplies(content: string): string {
  const lines = content.split('\n');
  const stripped = lines.filter(line => !line.startsWith('>') && !line.startsWith('On ') || !line.includes(' wrote:'));
  return stripped.join('\n').trim();
}

// ── Avatar ─────────────────────────────────────────────────────────

function Avatar({ name, size = 36 }: { name: string; size?: number }): ReactNode {
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

  useEffect(() => {
    if (isSelected && ref.current) {
      ref.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [isSelected]);

  return (
    <button
      ref={ref}
      onClick={onClick}
      className="w-full text-left px-3 py-2.5 flex items-center gap-2.5 transition-colors"
      style={{
        background: isSelected ? getDomainColorWithAlpha('messages', '18') : "transparent",
        borderLeft: `2px solid ${isSelected ? msgColor : "transparent"}`,
      }}
    >
      <Avatar name={name} size={36} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-1 mb-0.5">
          <span
            className="text-sm font-medium truncate"
            style={{ color: isSelected ? 'rgb(var(--canvas-fg-1))' : 'rgb(var(--canvas-fg-2))' }}
          >
            {name}
          </span>
          <span className="text-xs shrink-0" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            {formatTimeAgo(source.updated_at)}
          </span>
        </div>
        <div className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          {source.chunk_count} {source.chunk_count === 1 ? "message" : "messages"}
        </div>
      </div>
    </button>
  );
}

// ── ErrorState ────────────────────────────────────────────────────

function ErrorState(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: 'rgb(var(--status-error) / 0.13)' }}
      >
        <span style={{ color: 'rgb(var(--status-error))' }}>
          <Icon name="alert" size={32} />
        </span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
          Failed to load messages
        </p>
        <p style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>
          There was a problem fetching the thread.
        </p>
      </div>
    </div>
  );
}

// ── TimestampDivider ───────────────────────────────────────────────

function TimestampDivider({ timestamp }: { timestamp: string }): ReactNode {
  const d = new Date(timestamp);
  const label = isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
  return (
    <div className="flex items-center gap-3 my-3 px-4">
      <div className="flex-1 h-px" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
      <span className="text-xs shrink-0" style={{ color: 'rgb(var(--canvas-fg-3))' }}>{label}</span>
      <div className="flex-1 h-px" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
    </div>
  );
}

// ── MessageThread (with ChatMessage) ──────────────────────────────

const PAGE_SIZE = 50;

type DisplayItem =
  | { kind: "divider"; timestamp: string; key: string }
  | { kind: "message"; chunk: ChunkResponse; meta: MessageMeta; key: string };

type ThreadState = {
  startOffset: number;
  loaded: ChunkResponse[];
};

type ThreadAction =
  | { type: "reset"; startOffset: number }
  | { type: "setStartOffset"; startOffset: number }
  | { type: "accumulateChunks"; chunks: ChunkResponse[] };

function threadReducer(state: ThreadState, action: ThreadAction): ThreadState {
  switch (action.type) {
    case "reset":
      return { startOffset: action.startOffset, loaded: [] };
    case "setStartOffset":
      return { ...state, startOffset: action.startOffset };
    case "accumulateChunks": {
      const seen = new Set(state.loaded.map((c) => c.chunk_hash));
      const fresh = action.chunks.filter((c) => !seen.has(c.chunk_hash));
      if (fresh.length === 0) return state;
      return { ...state, loaded: [...fresh, ...state.loaded] };
    }
    default:
      return state;
  }
}

function MessageThread({ source }: { source: SourceSummary }): ReactNode {
  const bottomRef = useRef<HTMLDivElement>(null);
  const hasScrolledToBottom = useRef(false);
  const name = conversationName(source);

  const [state, dispatch] = useReducer(threadReducer, {
    startOffset: Math.max(0, source.chunk_count - PAGE_SIZE),
    loaded: [],
  });

  useEffect(() => {
    hasScrolledToBottom.current = false;
    dispatch({
      type: "reset",
      startOffset: Math.max(0, source.chunk_count - PAGE_SIZE),
    });
  }, [source.source_id, source.chunk_count]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["chunks", source.source_id, state.startOffset],
    queryFn: () => fetchSourceChunks(source.source_id, undefined, PAGE_SIZE, state.startOffset),
    staleTime: Infinity,
  });

  useEffect(() => {
    if (!data?.chunks || data.source_id !== source.source_id) return;
    dispatch({ type: "accumulateChunks", chunks: data.chunks });
  }, [data, source.source_id]);

  useEffect(() => {
    if (!isLoading && state.loaded.length > 0 && !hasScrolledToBottom.current) {
      const timer = setTimeout(() => {
        bottomRef.current?.scrollIntoView({ behavior: "instant" });
        hasScrolledToBottom.current = true;
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [isLoading, state.loaded.length]);

  const hasEarlier = state.startOffset > 0;
  const isPaginating = isLoading && state.loaded.length > 0;

  function loadEarlier(): void {
    dispatch({ type: "setStartOffset", startOffset: Math.max(0, state.startOffset - PAGE_SIZE) });
  }

  const items = useMemo((): DisplayItem[] => {
    const sorted = [...state.loaded].sort((a, b) => {
      const ta = typeof a.domain_metadata?.timestamp === "string" ? a.domain_metadata.timestamp : "";
      const tb = typeof b.domain_metadata?.timestamp === "string" ? b.domain_metadata.timestamp : "";
      return ta.localeCompare(tb);
    });

    const result: DisplayItem[] = [];
    let lastTs: Date | null = null;

    for (const chunk of sorted) {
      const meta = extractMessageMeta(chunk);
      if (!meta) continue;

      const msgDate = new Date(meta.timestamp);
      const valid = !isNaN(msgDate.getTime());

      if (valid) {
        if (!lastTs) {
          result.push({ kind: "divider", timestamp: meta.timestamp, key: `div-first-${chunk.chunk_hash}` });
        } else if (msgDate.getTime() - lastTs.getTime() > 60 * 60 * 1_000) {
          result.push({ kind: "divider", timestamp: meta.timestamp, key: `div-${chunk.chunk_hash}` });
        }
        lastTs = msgDate;
      }

      result.push({ kind: "message", chunk, meta, key: chunk.chunk_hash });
    }
    return result;
  }, [state.loaded]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Thread header */}
      <div
        className="px-5 py-3 shrink-0 flex items-center gap-3"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}
      >
        <Avatar name={name} size={32} />
        <div>
          <div className="text-sm font-semibold" style={{ color: 'rgb(var(--canvas-fg-1))' }}>{name}</div>
          <div className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            {source.chunk_count} {source.chunk_count === 1 ? "message" : "messages"}
          </div>
        </div>
      </div>

      {/* Scrollable messages */}
      <div className="flex-1 overflow-y-auto py-2" style={{ background: 'rgb(var(--canvas-bg))' }}>
        {isError ? (
          <ErrorState />
        ) : (
          <>
            {hasEarlier && (
              <div className="flex justify-center py-3">
                {isPaginating ? (
                  <div
                    className="w-4 h-4 rounded-full border-2 animate-spin"
                    style={{ borderColor: `rgb(var(--canvas-fg-3)) transparent transparent transparent` }}
                  />
                ) : (
                  <button
                    onClick={loadEarlier}
                    className="px-4 py-1.5 rounded-full text-xs font-medium transition-opacity hover:opacity-75"
                    style={{
                      background: 'rgb(var(--canvas-surface))',
                      color: 'rgb(var(--canvas-fg-2))',
                      border: `1px solid rgb(var(--canvas-border))`,
                    }}
                  >
                    Load earlier messages
                  </button>
                )}
              </div>
            )}

            {isLoading && state.loaded.length === 0 && (
              <div className="px-4 py-4 space-y-4">
                {[40, 65, 50, 30, 60].map((w, i) => (
                  <div key={i} className={`flex ${i % 2 ? "justify-end" : "justify-start"}`}>
                    <div
                      className="h-9 rounded-2xl animate-pulse"
                      style={{ width: `${w}%`, background: 'rgb(var(--canvas-bg-2))' }}
                    />
                  </div>
                ))}
              </div>
            )}

            {items.map((item) =>
              item.kind === "divider" ? (
                <TimestampDivider key={item.key} timestamp={item.timestamp} />
              ) : (
                <ChatMessage
                  key={item.key}
                  role={item.meta.is_from_me ? "user" : "bot"}
                  senderName={item.meta.is_from_me ? "Me" : item.meta.sender}
                  timestamp={formatMessageTimestamp(item.meta.timestamp)}
                  body={<span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{stripQuotedReplies(item.chunk.content)}</span>}
                  className="px-4"
                />
              ),
            )}

            {!isLoading && state.loaded.length === 0 && (
              <div className="flex items-center justify-center h-32">
                <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  No messages found.
                </p>
              </div>
            )}

            <div ref={bottomRef} />
          </>
        )}
      </div>

      {/* Read-only archive banner */}
      <div
        className="shrink-0 flex items-center justify-center gap-2 py-2 px-4"
        style={{ borderTop: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}
      >
        <span style={{ color: 'rgb(var(--canvas-fg-2))' }}>
          <Icon name="lock" size={14} className="shrink-0" />
        </span>
        <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
          Archive — read only. This is historical data, not a live messenger.
        </span>
      </div>
    </div>
  );
}

// ── MetadataSidebar ────────────────────────────────────────────────

function MetadataSidebar({ source }: { source: SourceSummary }): ReactNode {
  const name = conversationName(source);

  // Fetch a page of chunks to extract participants and date range
  const { data: chunksData } = useQuery({
    queryKey: ["thread-meta", source.source_id],
    queryFn: () => fetchSourceChunks(source.source_id, undefined, 100, 0),
    staleTime: Infinity,
  });

  const { participants, dateRange } = useMemo(() => {
    if (!chunksData?.chunks) {
      return {
        participants: [name],
        dateRange: formatDateRange(source.created_at, source.updated_at),
      };
    }

    const senderSet = new Set<string>();
    let minTs = source.updated_at;
    let maxTs = source.created_at;

    for (const chunk of chunksData.chunks) {
      const meta = extractMessageMeta(chunk);
      if (!meta) continue;
      if (!meta.is_from_me && meta.sender) senderSet.add(meta.sender);
      if (meta.timestamp) {
        if (meta.timestamp < minTs) minTs = meta.timestamp;
        if (meta.timestamp > maxTs) maxTs = meta.timestamp;
      }
    }

    return {
      participants: senderSet.size > 0 ? Array.from(senderSet) : [name],
      dateRange: formatDateRange(minTs, maxTs),
    };
  }, [chunksData, source, name]);

  const kvRows = [
    {
      key: 'Participants',
      value: (
        <div className="flex flex-col gap-0.5">
          {participants.map((p, i) => (
            <span key={i} style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-2))' }}>{p}</span>
          ))}
        </div>
      ),
    },
    {
      key: 'Messages',
      value: source.chunk_count.toLocaleString(),
    },
    {
      key: 'Date range',
      value: dateRange,
    },
    {
      key: 'Source',
      value: adapterLabel(source.adapter_id),
    },
  ];

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: 'rgb(var(--canvas-surface))' }}
    >
      <div
        className="px-4 py-3 shrink-0"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          Thread Info
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <KVGrid rows={kvRows} keyWidth={90} />
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
        style={{ width: 48, height: 48, background: getDomainColorWithAlpha('messages', '20') }}
      >
        <ChatBubbleLeftIcon className="w-6 h-6" style={{ color: msgColor }} />
      </div>
      <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
        Select a conversation to view messages
      </p>
    </div>
  );
}

// ── MessagesPage ──────────────────────────────────────────────────

export default function MessagesPage(): ReactNode {
  const navigate = useNavigate();
  const { thread_id: selectedThreadId } = useSearch({ from: "/messages" });
  const [filterText, setFilterText] = useState("");

  const sourcesQuery = useSources({ domain: "messages", limit: 500 });
  const sources = useMemo(() => sourcesQuery.data?.sources ?? [], [sourcesQuery.data]);

  // Collect unique adapter prefixes for filter dropdown
  const adapterPrefixes = useMemo(() => {
    const set = new Set<string>();
    for (const s of sources) set.add(s.adapter_id.split(':')[0]);
    return Array.from(set).sort();
  }, [sources]);

  const [activeAdapterFilters, setActiveAdapterFilters] = useState<string[]>([]);

  const filteredSources = useMemo(() => {
    let list = sources;
    if (activeAdapterFilters.length > 0) {
      list = list.filter(s => activeAdapterFilters.includes(s.adapter_id.split(':')[0]));
    }
    if (filterText.trim()) {
      const q = filterText.toLowerCase();
      list = list.filter((s) => {
        const name = conversationName(s).toLowerCase();
        return name.includes(q) || s.origin_ref.toLowerCase().includes(q);
      });
    }
    return [...list].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
  }, [sources, filterText, activeAdapterFilters]);

  const selectedSource = useMemo(
    () => sources.find((s) => s.source_id === selectedThreadId) ?? null,
    [sources, selectedThreadId],
  );

  function selectThread(sourceId: string): void {
    void navigate({ to: "/messages", search: { thread_id: sourceId } });
  }

  const adapterFilterSummary = activeAdapterFilters.length > 0
    ? `${activeAdapterFilters.length} selected`
    : 'All';

  const threadListPanel = (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-surface))' }}>
      {/* Search + filter bar */}
      <div
        className="px-3 py-2 shrink-0 flex items-center gap-2"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        <div
          className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg flex-1"
          style={{ background: 'rgb(var(--canvas-bg))' }}
        >
          <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            <Icon name="search" size={14} className="shrink-0" />
          </span>
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Search conversations…"
            className="flex-1 bg-transparent text-xs outline-none"
            style={{ color: 'rgb(var(--canvas-fg-1))' }}
          />
        </div>
        {adapterPrefixes.length > 1 && (
          <FilterDropdown
            mode="checkbox"
            value={activeAdapterFilters}
            onChange={setActiveAdapterFilters}
          >
            <FilterDropdown.Trigger label="Source" summary={adapterFilterSummary} />
            <FilterDropdown.Panel>
              <FilterDropdown.Section title="Source adapter">
                {adapterPrefixes.map(prefix => (
                  <FilterDropdown.Checkbox
                    key={prefix}
                    value={prefix}
                    label={prefix.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                  />
                ))}
              </FilterDropdown.Section>
            </FilterDropdown.Panel>
          </FilterDropdown>
        )}
      </div>

      {/* Count row */}
      <div className="px-4 py-1.5 shrink-0">
        <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          {filteredSources.length} {filteredSources.length === 1 ? "conversation" : "conversations"}
        </span>
      </div>

      {/* Scrollable conversation list */}
      <div className="flex-1 overflow-y-auto">
        {sourcesQuery.isLoading ? (
          <div className="px-3 py-2 space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex items-center gap-2.5 animate-pulse">
                <div className="rounded-full shrink-0" style={{ width: 36, height: 36, background: 'rgb(var(--canvas-surface))' }} />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 rounded" style={{ width: "60%", background: 'rgb(var(--canvas-surface))' }} />
                  <div className="h-2.5 rounded" style={{ width: "80%", background: 'rgb(var(--canvas-surface))' }} />
                </div>
              </div>
            ))}
          </div>
        ) : sourcesQuery.isError ? (
          <div className="px-4 py-6 text-center">
            <div className="flex justify-center mb-3" style={{ color: 'rgb(var(--status-error))' }}>
              <Icon name="alert" size={24} />
            </div>
            <p className="text-xs" style={{ color: 'rgb(var(--canvas-fg-2))' }}>Failed to load conversations</p>
          </div>
        ) : filteredSources.length === 0 ? (
          <div className="px-4 py-6 text-center">
            <p className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              {filterText ? "No conversations match your search" : "No conversations found"}
            </p>
          </div>
        ) : (
          filteredSources.map((source) => (
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
  );

  const threadViewPanel = (
    <div className="h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      {selectedSource ? <MessageThread source={selectedSource} /> : <EmptyState />}
    </div>
  );

  const metadataPanel = (
    <div className="h-full overflow-hidden">
      {selectedSource ? (
        <MetadataSidebar source={selectedSource} />
      ) : (
        <div className="flex items-center justify-center h-full">
          <p className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            Select a conversation
          </p>
        </div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Domains"
        title="Messages"
        subtitle="iMessage conversation history"
      />
      <div className="flex-1 min-h-0 overflow-hidden">
        <SplitPane
          direction="horizontal"
          initialSplitPercent={25}
          minSize={200}
          first={threadListPanel}
          second={
            <SplitPane
              direction="horizontal"
              initialSplitPercent={72}
              minSize={300}
              first={threadViewPanel}
              second={metadataPanel}
            />
          }
        />
      </div>
    </div>
  );
}
