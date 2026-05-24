# UX Refresh Implementation Plan

## Executive Summary

This document outlines the plan to update the Context Library UI to match the comprehensive design refresh in `/ui/design`. The refresh brings the UI into full alignment with the **Heimdall Design System v0.0.1** (Amber accent, two-surface architecture), introduces sophisticated versioning workflows (hash-set diffs, lineage rails, chunk provenance), and establishes consistent patterns across all domain views.

**Key Goals:**
1. Maximize re-use of Heimdall Design System components, replacing all custom equivalents
2. Fix design token misalignment (accent color, domain colors)
3. Implement versioning-first workflows (source detail, chunk inspector)
4. Standardize domain view patterns (three-pane layouts, chunk markers, version pills)
5. Expand APIs to support new data requirements

---

## Design System Audit

### Heimdall UI Package (v0.0.1) — Actual Component APIs

All 28 components with their actual prop signatures, verified against source.

#### Primitives

**`Icon`** — SVG icon renderer.
```tsx
<Icon name={IconName} size={number} className={string} />
```
Available icon names (camelCase): `dashboard`, `search`, `bell`, `plus`, `check`, `x`, `chevronDown`, `chevronUp`, `chevronLeft`, `chevronRight`, `menu`, `settings`, `alert`, `trash`, `edit`, `download`, `upload`, `eye`, `eyeOff`, `clock`, `calendar`, `filter`, `link`, `lock`, `unlock`, `user`, `copy`, `info`, `help`, `spinner`, `loading`, `moreVertical`, `moreHorizontal`, `reload`, `arrowRight`, `arrowLeft`, `arrowUp`, `arrowDown`, `star`, `heart`, `palette`, `component`, `table`, `layout`, `moon`, `sun`, `schema`, `data`, `pipeline`, `graph`.

⚠️ **Many design-spec icons are NOT in the Heimdall set.** Missing icons include: `brain`, `globe`, `shield`, `zap`, `layers`, `doc`, `cpu`, `flask`, `sparkle`, `history`, `tag`, `dot`, `expand`, `branch`, `database`, `folder`, `workflow`. Use `@heroicons/react/24/outline` (already a project dependency) for missing icons. Map the most common gaps:
- `doc` / notes → `DocumentTextIcon` (Heroicons)
- `cpu` / adapters → `CpuChipIcon` (Heroicons)
- `globe` / messages → `GlobeAltIcon` (Heroicons)
- `music` → `MusicalNoteIcon` (Heroicons)
- `location` / map → `MapPinIcon` (Heroicons)
- `people` → `UsersIcon` (Heroicons)
- `health` → `HeartIcon` (Heroicons, same as `heart` in Heimdall)
- `history` → `ClockIcon` (Heroicons, same as `clock` in Heimdall)

**`Button`** — Action button.
```tsx
<Button variant={'primary'|'secondary'|'ghost'|'danger'|'link'} size={'sm'|'md'}>…</Button>
```
Default: `variant="primary"`, `size="md"`.

**`Chip`** — Inline status/identity chip. The primary semantic label component.
```tsx
<Chip variant={'emerald'|'amber'|'rose'|'cyan'|'violet'|'neutral'} form={'default'|'id-tag'|'version'|'env'}>…</Chip>
```
- `form="default"` — renders a colored dot before children; use `variant` for color. Use for status labels (ok, running, warn, error).
- `form="id-tag"` — renders as a neutral identifier tag (no dot). For identifiers like `localhost:8000`, source IDs.
- `form="version"` — renders with amber styling, no dot. **Use for version pills (`v1`, `v2`, `v3`).**
- `form="env"` — renders with an env-colored dot. For environment indicators (`chroma · ok`).

**`Badge`** — Small compact inline badge (not for status; for counts and short labels).
```tsx
<Badge color={'emerald'|'amber'|'rose'|'cyan'|'violet'|'neutral'} pulse={boolean}>…</Badge>
```
`StatusBadge` — block-level status indicator row with dot and label.

#### Forms

**`TextInput`** — Styled `<input type="text">`.
```tsx
<TextInput mono={boolean} error={boolean} placeholder="…" value={…} onChange={…} />
```
`mono` adds monospace font — use for query inputs, identifier searches, hash displays.

**`Select`** — Styled native `<select>` element (NOT a custom dropdown popover).
```tsx
<Select error={boolean}><option>…</option></Select>
```
⚠️ **This is a native `<select>`, not a flyout dropdown.** The design's `fd-trigger` filter dropdowns (with flyout panels) need a custom `FilterDropdown` component built with a `<button>` trigger and absolute-positioned popover.

**`TriState`** — Three-state checkbox (checked / unchecked / indeterminate).
```tsx
<TriState indeterminate={boolean} checked={boolean} onChange={…} />
```
⚠️ **Not a segmented control.** The design's vector/rerank/hybrid toggle needs a Button group (multiple `<Button variant="secondary">` rendered side-by-side), not `TriState`.

**`Field`** — Form field wrapper with label and optional error message.

**`TextArea`**, **`NumberInput`** — Additional form inputs.

#### Data Display

**`StatTile`** — Single metric tile with optional delta.
```tsx
<StatTile
  label="SOURCES"
  value="4,812"
  color={'cyan'|'violet'|'amber'|'emerald'}
  delta={{ value: 38, label: '24h', direction: 'up' | 'down' }}
/>
```
Colors available: `cyan`, `violet`, `amber`, `emerald`. Map to dashboard metrics:
- `amber` → Sources, `emerald` → Active Chunks, `cyan` → Embeddings, `violet` → Versions.

**`StatGrid`** — Grid layout for StatTile children.
```tsx
<StatGrid columns={4}>
  <StatTile … /> {/* × 4 */}
</StatGrid>
```

**`Table`** — Data table with sorting and row selection.
```tsx
<Table<T>
  columns={[{ key, label, sortable?, width?, render?: (value, row, index) => ReactNode }]}
  data={T[]}
  rowKey={keyof T | (row, index) => string|number}
  selectable={boolean}
  selectedRows={[]}
  onSelectRows={fn}
  onSort={(key, direction) => void}
/>
```
The `render` function on each column enables custom cell content (domain bars, version chips, status chips).

#### Shell Framework

**`ShellLayout`** — Full app shell composing all shell components.
```tsx
<ShellLayout
  appTitle={{ title, version, collapsed?, hide? }}
  topbar={{ breadcrumbs, searchPlaceholder, onSearch, children, hide? }}
  sidebar={{ sections, activeItemId, collapsed?, onCollapse?, onSelectItem? }}
  statusbar={{ left, center, right, hide? }}
>
  {/* canvas content */}
</ShellLayout>
```

**`AppTitle`** — Brand area at top of sidebar.
```tsx
<AppTitle title="Context Library" version="versioned RAG" collapsed={boolean} />
```

**`Titlebar`** — Window chrome titlebar (macOS-style).
```tsx
<Titlebar left={ReactNode} center={ReactNode} right={ReactNode} />
```

**`Topbar`** — Workspace topbar with breadcrumbs and actions.
```tsx
<Topbar
  breadcrumbs={[{ label, href?, onClick? }]}
  searchPlaceholder="…"
  onSearch={(q) => void}
>
  {/* right-side custom content: env chips, icon buttons */}
</Topbar>
```
Place ws-chip, env-pill, notification buttons, and settings in `children`.

**`Statusbar`** — Bottom status bar.
```tsx
<Statusbar left={ReactNode} center={ReactNode} right={ReactNode} />
```

**`Sidebar`** — Left navigation sidebar.
```tsx
<Sidebar
  sections={[{ title: string, items: [{ id, label, icon?: IconName, count?, children? }] }]}
  activeItemId={string}
  collapsed={boolean}
  onCollapse={(collapsed) => void}
  onSelectItem={(id) => void}
/>
```
⚠️ **`icon` only accepts `IconName`** — cannot render custom domain dots. The domain section items (with colored dots) need a custom sidebar section rendered via `NavItem` with manual CSS dot elements, outside the `Sidebar` component's item list, OR pass domain items as a separate section and style with CSS overrides.

**`NavItem`** — Individual nav button.
```tsx
<NavItem icon={IconName} label="Notes" count={1284} active={boolean} depth={0|1} onClick={fn} />
```

#### Navigation

**`TabBar`** — Tab strip.
```tsx
<TabBar tabs={[{ id, label, count? }]} activeTabId={string} onSelectTab={(id) => void} />
```

**`CommandPalette`** — Full-screen searchable command palette.
```tsx
<CommandPalette
  isOpen={boolean}
  onClose={fn}
  commands={[{ id, label, description?, icon?: IconName, onSelect }]}
  placeholder="…"
/>
```

#### Dialogs

**`Modal`** — Centered dialog. `title` and `subtitle` are strings only; custom header content goes inside `children`.
```tsx
<Modal isOpen={boolean} onClose={fn} title="…" subtitle="…" footer={ReactNode}>…</Modal>
```

**`Drawer`** — Side drawer.
```tsx
<Drawer isOpen={boolean} onClose={fn} title="…" position={'left'|'right'} width="320px">…</Drawer>
```

**`ConfirmDialog`** — Confirmation modal.

**`Toast`** / **`ToastProvider`** — Notification toasts.

#### Containers

**`Panel`** — Content card with optional header.
```tsx
<Panel title="Domain Breakdown" subtitle="…" footer={ReactNode} bordered={boolean}>
  {/* body content */}
</Panel>
```
⚠️ **`title` and `subtitle` are strings only.** Custom panel headers with icons, counts, and action buttons need to be built outside the Panel prop system: do NOT pass `title` and instead render your own header inside `children` or above the `<Panel>`.

**`SplitPane`** — Resizable two-pane layout.
```tsx
<SplitPane
  direction={'horizontal'|'vertical'}
  initialSplitPercent={35}
  minSize={200}
  maxSize={600}
  first={<LeftPane />}
  second={<RightPane />}
/>
```
⚠️ **Only two panes.** The Notes design (three-pane: file tree | markdown reader | outline) requires either:
- Nested `SplitPane`: outer horizontal split (tree | rest), inner horizontal split (reader | outline).
- Or a CSS grid column layout when fixed-width panels are preferred.

**`Drawer`** — see Dialogs above.

---

### Token System

Tokens are defined as space-separated RGB channel values for use with `rgb(var(--token))` or `rgb(var(--token) / 0.5)`.

**Shell surface tokens** (always dark `#0F1729`):
```
--shell-bg, --shell-bg-2, --shell-surface, --shell-surface-2
--shell-border, --shell-border-2
--shell-fg-1 … --shell-fg-4
```

**Canvas surface tokens** (light default `#FFFFFF`):
```
--canvas-bg, --canvas-bg-2, --canvas-surface, --canvas-card
--canvas-fg-1 … --canvas-fg-4
--canvas-border, --canvas-border-strong
```

**Accent tokens** (AMBER):
```
--accent-primary: 251 191 36     /* #FBBF24 — amber-400 */
--accent-primary-hover: 245 158 11
--accent-primary-deep: 180 83 9
```

**Semantic status tokens**:
```
--status-ok, --status-ok-bg, --status-ok-fg
--status-warn, --status-warn-bg, --status-warn-fg
--status-error, --status-error-bg, --status-error-fg
--status-cyan, --status-emerald, --status-amber, --status-rose, --status-violet, --status-neutral
--semantic-{color}-fg/bg/border  (for chip-like backgrounds)
```

**Shape tokens**: `--radius-sm: 4px`, `--radius-md: 6px`, `--radius-lg: 8px`, `--radius-xl: 12px`

---

### Current Implementation Issues

1. **Wrong accent color**: `index.css` sets `--accent-primary: 99 102 241` (indigo), overriding Heimdall's amber. Must be removed.

2. **Wrong domain color token names**: `index.css` and `designTokens.ts` use `--domain-*` prefix (e.g., `--domain-notes`). The Heimdall package's own CSS does not define these. They are app-level tokens that must be defined in `index.css`. Currently set to incorrect colors (indigo accent for notes, etc.).

3. **`DomainBadge` component uses hardcoded Tailwind classes**: `components/shared/DomainBadge.tsx` uses `bg-blue-100 text-blue-800` etc., ignoring design tokens and the `Chip` component. Replace with `<Chip form="id-tag">` + domain color via inline style, or a domain-aware wrapper.

4. **`layoutConfig.ts` ICON_MAP is imprecise**: Maps domain nav icons to approximate Heimdall equivalents (e.g., `messages → 'info'`, `location → 'link'`, `music → 'palette'`). These are semantic mismatches. Better mappings are documented below.

5. **Panel custom headers**: Several routes render custom panel titles (with icons, counts, buttons) but should not pass `title` to the Panel component. Correct pattern: omit `title`, render custom header in children.

6. **`TriState` misuse potential**: Plan was previously suggesting `TriState` for segmented controls. Use Button groups instead.

---

## Screen-by-Screen Analysis

### 1. Overview / Dashboard

**Design Refresh Vision:**
- **Stat grid** (4 tiles): Sources, Active Chunks, Embeddings, Versions with delta indicators
- **Domain breakdown panel**: Grid of domain tiles with adapters listed, chunk counts, color bars
- **Active pipelines panel**: Mini-pipeline progress indicators with step markers
- **Recent activity feed**: Timeline of ingests/updates/errors with icons and metadata
- Chip indicators for system health (emerald = healthy)
- Page actions: "Re-poll all", "Add adapter"

**Current Implementation (`routes/index.tsx`):**
- ✅ Has StatTile usage for basic stats
- ✅ Has domain cards with routing
- ✅ Has activity feed from recent sources
- ❌ Stat tiles don't show deltas or metadata
- ❌ Domain cards lack adapter pills, chunk counts, color bars
- ❌ No pipeline activity panel
- ❌ No system health chip in page header
- ❌ Activity feed lacks proper timeline formatting and icons

**Implementation Tasks:**
1. Update stat tiles to use StatGrid with delta indicators
2. Rebuild domain cards to match design:
   - Add domain color bar (3px left edge)
   - List adapter pills below count
   - Show "X adapters · Y chunks" metadata
   - Use Panel component with proper spacing
3. Create PipelineActivityPanel component:
   - Mini-pipeline step indicators (6 steps: fetch/normalize/diff/chunk/embed/store)
   - Progress bar with step highlighting
   - Status chips (running/idle/warn)
   - Version badges
4. Enhance activity feed:
   - Add activity type icons (create/update/run/error)
   - Format with proper mono font for identifiers
   - Add tag badges (VERSION/EMBED/POLL/SOURCE/ERROR)
   - Show "when" timestamp relative format
5. Add page header with system health chip

**API Expansion Needed:**
- `GET /admin/pipelines` - active pipeline status with current step
- `GET /stats/activity` - structured activity feed (currently derived from sources)

---

### 2. Search

**Design Refresh Vision:**
- **Hero search card**: Large input with filters row below
  - Domain/Adapter/Source/When/Top-K filter dropdowns
  - Vector/Rerank/Hybrid segmented control
  - Query stats: "7 results · 84 ms · 12 ms rerank"
- **Result cards** with:
  - Domain dot and color bar
  - Source path (mono font)
  - Section breadcrumb (mono, muted)
  - Version pill + HEAD chip
  - Similarity score (0.0–1.0) with colored bar
  - Snippet with `<mark>` highlights
  - Metadata row: chunk hash (truncated), "ingested X ago", adapter, parent hash, normalizer version
- **Facets sidebar**: Domain/adapter/date range selectors
- **Sort controls**: Similarity/Recency/Source toggle

**Current Implementation (`routes/search.tsx`):**
- ✅ Search input and results list
- ✅ Domain filtering chip toggles
- ✅ `ScoreBar` component for similarity scores (already implemented)
- ✅ Keyword highlighting with regex capture (already implemented)
- ✅ `Drawer` from Heimdall already used for result detail panel
- ❌ No hero card layout (filters not organized as filter row)
- ❌ No `FilterDropdown` flyouts (uses inline chip toggles)
- ❌ Result cards lack: version pills, lineage metadata (parent hash, normalizer, adapter)
- ❌ No segmented mode toggle (vector/rerank/hybrid)
- ❌ No facets sidebar
- ❌ No sort toggle (similarity/recency/source)

**Implementation Tasks:**
1. Build SearchHeroCard layout:
   - Use `TextInput mono` from Heimdall for query (already in use)
   - Build filter row with custom `FilterDropdown` for domain/adapter/source/when/top-K (NOT Heimdall `Select`)
   - Add mode toggle using `Button` group (`variant="secondary"` → `variant="primary"` for active) for vector/rerank/hybrid
   - Show query stats eyebrow ("7 results · 84 ms · 12 ms rerank")
2. Enhance SearchResultCard:
   - Add 3px domain color bar on left edge
   - `<Chip form="version">v3</Chip>` for version
   - Keep existing `ScoreBar` for similarity
   - Add metadata row: `HashDisplay`, adapter `<Chip form="id-tag">`, parent hash, normalizer version
3. Add sort toggle: `Button` group (Similarity / Recency / Source)
4. Wire up reranker toggle to API (`rerank` mode)

**API Expansion Needed:**
- `POST /query` already supports `reranker` and `domain` filtering
- Add `include_provenance=true` param to return `parent_hash`, `adapter_id`, `normalizer_version` in each result

---

### 3. Sources Browser

**Design Refresh Vision:**
- **Tabs**: Sources / Chunks / Versions / Retired (with counts)
- **Filter row**: Domain/Adapter/Versions/LastFetched dropdowns + search input
- **Data table** with columns:
  - Domain color bar (3px)
  - SOURCE_ID (mono font)
  - DOMAIN (dot + label)
  - ADAPTER (mono)
  - VER (version pill)
  - CHUNKS (count)
  - LAST FETCHED (mono, relative)
  - STATE (chip: ok/updated/new/done/in-progress)
  - Actions (kebab menu)
- **Pagination** with "14 OF 4,812 · 1 SELECTED" eyebrow
- **Page actions**: "Filters · 2", "Export CSV"

**Current Implementation (`routes/browser.tsx`):**
- ✅ Has TabBar with Sources/Chunks/Versions
- ✅ Uses DataTable component
- ✅ Has domain filtering
- ❌ Missing filter dropdown row
- ❌ Table lacks domain color bars
- ❌ No version pills in table
- ❌ No state chips
- ❌ Pagination shows different format
- ❌ No "Filters · 2" active filter indicator

**Implementation Tasks:**
1. Replace tab implementation with TabBar from Heimdall (already using it)
2. Add FilterRow component with Select dropdowns for domain/adapter/versions/lastFetched
3. Update DataTable columns:
   - Prepend domain color bar column (render as 3px colored div)
   - Add VersionPill component to VER column
   - Add StatusChip component to STATE column
   - Use mono font for SOURCE_ID, ADAPTER, LAST FETCHED
4. Add active filter count to "Filters" button
5. Enhance pagination footer with "X OF Y · Z SELECTED" format

**API Expansion Needed:**
- `GET /sources` already supports domain/adapter filtering
- Add `last_fetched` time range filter
- Add `state` filter (active/retired/new/updated)
- Add bulk actions endpoint for CSV export

---

### 4. Source Detail (NEW)

**Design Refresh Vision:**
- **Page header**: Source path (mono, h1 size), subtitle with version count, chunk stats
- **Source meta panel**: KV grid with SOURCE_ID, ADAPTER, POLL STRATEGY, CURRENT VER, CHUNKS, LAST FETCHED
- **Two-column layout**:
  - **Versions timeline** (left, 320px): List of versions with:
    - Version label (v1, v2, v3) with HEAD badge
    - Headline + summary
    - Add/Remove/Keep counts
    - Timestamp
    - Active state highlighting
  - **Diff view** (right): Hash-set diff or content diff
    - FROM/TO version selectors
    - Hash-set diff: Three columns (Added/Retired/Kept)
    - Each hash with chunk position/section
    - Content diff: Side-by-side markdown with +/- highlighting
    - Toggle: hash diff / content diff / raw markdown

**Current Implementation:**
- ❌ **MISSING ENTIRELY**
- Browser page shows source list but no detail view
- `routes/browser.versions.$sourceId.tsx` has basic version history but no timeline UI

**Implementation Tasks:**
1. Create `routes/sources.$sourceId.tsx` (new route)
2. Build SourceDetailHeader component:
   - Source path in mono h1
   - Subtitle with stats
   - Page actions (Re-poll, Open in app, Reprocess)
3. Create SourceMetaPanel with KV grid layout
4. Create VersionTimeline component:
   - List of VersionTimelineItem components
   - Active state styling
   - HEAD badge on current version
   - Add/Remove/Keep mini-stats
5. Create HashSetDiffView component:
   - Three-column grid (Added/Retired/Kept)
   - Each column shows list of hash + position
   - Color-coded (green/red/neutral)
6. Create ContentDiffView component:
   - Side-by-side panes
   - Line-by-line diff with +/- highlighting
   - Use Panel component for structure
7. Add FROM/TO version selectors (Select components)
8. Add diff mode toggle (hash/content/raw)

**API Expansion Needed:**
- `GET /sources/{source_id}/versions` - list all versions with stats
- `GET /sources/{source_id}/versions/{from}/diff/{to}` - hash-set diff (added/removed/kept hashes with positions)
- `GET /sources/{source_id}/versions/{version}/content` - raw markdown content for diff

---

### 5. Chunk Inspector (NEW)

**Design Refresh Vision:**
- **Page header**: Chunk hash (mono h1), subtitle explaining content-addressing
- **Lineage rail panel**: Horizontal flow showing provenance:
  - adapter → normalize → source → domain.chunker → section → embedder → vector store
  - Each node as pill with icon
  - Arrows between nodes
- **Two-column layout**:
  - **Left (1.6fr)**: Context header + Content + Embedding
    - Context header: Mono block showing breadcrumb (EMBEDDED · NOT HASHED badge)
    - Content: Markdown rendering with code/pre blocks (HASHED · SHA-256 badge)
    - Embedding: Truncated vector display with dimension info
  - **Right (1fr)**: Version chain + Metadata + Actions
    - Version chain: List of ancestor chunks with version labels
    - Metadata: KV grid with source_id, domain, adapter, normalizer, embedding model
    - Related chunks panel

**Current Implementation:**
- ❌ **MISSING ENTIRELY**
- Browser page has chunks table but no detail/inspector view

**Implementation Tasks:**
1. Create `routes/chunks.$hash.tsx` (new route)
2. Build ChunkInspectorHeader component
3. Create LineageRail component:
   - Horizontal flex layout with pills and arrows
   - Each node: icon + label
   - Use Chip or Badge from Heimdall
4. Create ContextHeaderPanel component:
   - Panel with "EMBEDDED · NOT HASHED" badge
   - Mono text display
   - Token count eyebrow
5. Create ChunkContentPanel component:
   - Panel with "HASHED · SHA-256" badge
   - Markdown rendering
   - Token count + char count eyebrow
   - Tabs for markdown/normalized/raw
6. Create EmbeddingPanel component:
   - Truncated vector display (first 10 dims + "...")
   - Dimension info
   - Model name
7. Create VersionChainPanel component:
   - List of ancestor chunks
   - Version labels with → arrows
   - Click to navigate to ancestor
8. Create ChunkMetadataPanel with KV grid
9. Wire up navigation from chunks table to inspector

**API Expansion Needed:**
- `GET /chunks/{hash}/provenance` - full lineage (adapter, normalizer version, source, domain, chunk position, embedding model, parent hash)
- `GET /chunks/{hash}/ancestors` - version chain back to root chunk
- `GET /chunks/{hash}/embedding` - vector data (currently not exposed?)

---

### 6. Notes Domain View

**Design Refresh Vision:**
- **Three-pane layout** (260px | flex | 360px):
  - **Left**: File tree with folder collapse/expand, selected state, version counts
  - **Center**: Markdown reader with:
    - Header: filename (mono), version pill, HEAD chip, chunk count, history button
    - Tabs: rendered / chunked / raw markdown / cross-refs
    - Content with chunk markers (∙ chunk_01 · # Section · 7e3a91ff21…)
  - **Right**: Outline / inspector / cross-refs
- **File tree** with domain icons, version counts, search input
- **Chunk markers** inline in markdown showing chunk boundaries

**Current Implementation (`routes/notes.tsx`):**
- ✅ `SplitPane` from Heimdall already imported and used
- ✅ Source list in left pane (file tree precursor)
- ✅ Markdown rendering in right pane
- ✅ Uses `Chip form="default"` already for wikilinks (wiki link chips)
- ❌ Two-pane only; missing outline/inspector panel (needs nested `SplitPane`)
- ❌ No collapsible folder tree hierarchy (flat source list)
- ❌ No chunk markers in rendered markdown
- ❌ No `TabBar` for rendered/chunked/raw/cross-refs tabs

**Implementation Tasks:**
1. Extend to three-pane layout using nested `SplitPane`:
   ```tsx
   <SplitPane first={<FileTreePanel />} second={
     <SplitPane first={<MarkdownReaderPanel />} second={<OutlinePanel />} />
   } />
   ```
2. Enhance FileTreePanel:
   - Collapsible folder hierarchy (currently flat list)
   - `<Chip form="version">v3</Chip>` badge per file
   - `Icon name="chevronRight"` / `"chevronDown"` for expand/collapse
   - `TextInput` search at top
3. Enhance MarkdownReaderPanel:
   - Header: filename (mono h1), `<Chip form="version">`, `<Chip variant="amber">HEAD</Chip>`, chunk count
   - `TabBar` for rendered / chunked / raw / cross-refs
   - In chunked view: inject `<span className="chunk-mark">` at chunk boundaries
4. Add OutlinePanel:
   - Heading list from markdown AST
   - Click-to-scroll
   - Per-heading chunk count badge (`Badge`)

**API Expansion Needed:**
- `GET /sources/{source_id}/chunks` - already exists
- `GET /sources/{source_id}/outline` - extract heading structure (or client-side from markdown)
- `GET /sources/{source_id}/cross-refs` - references to other sources

---

### 7. Messages Domain View

**Design Refresh Vision:**
- **Three-pane layout**:
  - **Left**: Thread list (sender, subject, date, message count)
  - **Center**: Thread reader with individual messages
  - **Right**: Thread metadata, participants, attachments
- **Thread reader**: Each message as card with sender, timestamp, content
- **Quoted reply stripping** shown as "[quoted]" collapsed sections

**Current Implementation (`routes/messages.tsx`):**
- ✅ `SplitPane` from Heimdall already imported and used
- ✅ Thread list in left pane
- ✅ Thread message rendering in right pane
- ✅ Avatar rendering with initials
- ❌ Two-pane only; missing thread metadata sidebar (needs nested `SplitPane`)
- ❌ No thread metadata panel (participants, message count, date range)

**Implementation Tasks:**
1. Convert to three-pane layout
2. Create ThreadListPanel component:
   - List of threads with sender/subject/date/count
   - Selected state
   - Domain dot for message type (email vs iMessage)
3. Create ThreadReaderPanel component:
   - Vertical stack of message cards
   - Each message: avatar, sender, timestamp, content
   - Quoted reply indicators
4. Create ThreadMetadataPanel component:
   - Participants list
   - Attachment links
   - Thread stats

**API Expansion Needed:**
- `GET /sources/{source_id}/thread` - thread metadata (participants, message count)
- Thread data structure already in chunks

---

### 8. Events Domain View

**Design Refresh Vision:**
- **Calendar grid** (month/week/agenda views)
- **Event cards** with time, title, calendar source
- **Domain dots** for calendar source (caldav, apple.health workouts, apple.music)
- **Date navigation** with month/week/day toggles

**Current Implementation (`routes/events.tsx`):**
- ✅ Has calendar grid with month/week/agenda
- ✅ Good event rendering
- ❌ Could use more Heimdall components for controls
- ❌ Missing domain dots on events

**Implementation Tasks:**
1. Replace custom buttons with Button from Heimdall
2. Add domain dots to event cards
3. Use Button group for view mode toggle (month/week/day)
4. Use Select for date navigation

---

### 9. Tasks Domain View

**Design Refresh Vision:**
- **Kanban board** (To Do / In Progress / Done columns)
- **Task cards** with:
  - Title, checkbox (state)
  - Due date, priority indicator
  - Source badge (reminders, obsidian.tasks, caldav)
  - Version indicator for state changes
- **Lifecycle timeline** showing state transitions

**Current Implementation (`routes/tasks.tsx`):**
- ✅ Has task list view
- ❌ Not kanban layout
- ❌ No lifecycle timeline
- ❌ Missing visual state indicators

**Implementation Tasks:**
1. Create KanbanBoard component with three columns
2. Create TaskCard component:
   - Checkbox with state
   - Title (h3)
   - Metadata row: due date, priority, source
   - Version indicator showing state change count
3. Create LifecycleTimeline component (in sidebar):
   - List of state transitions with timestamps
   - open → in-progress → done visualization

**API Expansion Needed:**
- `GET /sources/{source_id}/lifecycle` - state transition history for task

---

### 10. Documents Domain View

**Design Refresh Vision:**
- **Two-pane layout**: Folder tree + File grid/list
- **File grid** with document type icons, chunk counts, last modified
- **File types**: PDF, markdown, code, images
- **Preview panel** for selected file

**Current Implementation (`routes/documents.tsx`):**
- ✅ Has folder tree + file grid
- ✅ Good file type detection
- ❌ Not using Heimdall components consistently
- ❌ Preview panel could be enhanced

**Implementation Tasks:**
1. Replace custom tree with collapsible Panel components
2. Use Button from Heimdall for view/sort controls
3. Enhance preview panel with tabs for rendered/chunks/raw
4. Add version pill if document has multiple versions

---

### 11. Health Domain View

**Design Refresh Vision:**
- **Time-series charts** for metrics (HRV, sleep, activity)
- **Date range selector** with presets (7d, 30d, 90d, custom)
- **Metric cards** showing current/avg/trend
- **Calendar heatmap** for activity overview

**Current Implementation (`routes/health.tsx`):**
- ✅ Has time-series rendering
- ✅ Good metric breakdown
- ❌ Charts could use design system styling
- ❌ Missing calendar heatmap

**Implementation Tasks:**
1. Use StatTile/StatGrid for metric cards
2. Style charts with design system colors (amber accent)
3. Create HeatmapCalendar component for activity overview
4. Use Select for date range presets

---

### 12. Location Domain View

**Design Refresh Vision:**
- **Map view** with place markers
- **Place list** sidebar with visit counts, last visit date
- **Visit timeline** for selected place
- **Heatmap overlay** for frequency

**Current Implementation (`routes/location.tsx`):**
- ✅ Has map view
- ✅ Has place list
- ❌ Timeline could be enhanced
- ❌ No heatmap overlay

**Implementation Tasks:**
1. Use Panel for place list sidebar
2. Create VisitTimeline component
3. Add heatmap overlay option (toggle)

---

### 13. People Domain View

**Design Refresh Vision:**
- **Contact cards** with name, avatar, metadata
- **Relationship graph** showing connections
- **Activity timeline** (messages, events with person)

**Current Implementation (`routes/people.tsx`):**
- ✅ Has contact list
- ❌ No relationship graph
- ❌ No activity timeline

**Implementation Tasks:**
1. Create ContactCard component with avatar, name, metadata
2. Create RelationshipGraph component (SVG-based)
3. Create ActivityTimeline component showing interactions

**API Expansion Needed:**
- `GET /people/{person_id}/relationships` - connections to other people
- `GET /people/{person_id}/activity` - timeline of interactions

---

### 14. Music Domain View

**Design Refresh Vision:**
- **Album grid** with cover art, artist, track count
- **Play history timeline**
- **Listening stats** (top artists, genres, decades)

**Current Implementation (`routes/music.tsx`):**
- ✅ Has album list
- ❌ No play history timeline
- ❌ No listening stats

**Implementation Tasks:**
1. Create AlbumGrid component with cover art
2. Create PlayHistoryTimeline component
3. Create ListeningStats panel with StatGrid

**API Expansion Needed:**
- `GET /music/play-history` - listening timeline
- `GET /music/stats` - aggregated listening data

---

### 15. Admin / Adapters View (NEW)

**Design Refresh Vision:**
- **Adapter cards** with status, last run, source count
- **Pipeline configuration** editor
- **Re-poll controls** per adapter
- **Adapter health indicators**

**Current Implementation (`routes/admin.tsx`):**
- ✅ Already uses `StatTile, StatGrid, Table, Button, StatusBadge, Badge, Select` from Heimdall
- ✅ Health tiles for SQLite/ChromaDB/Adapters with StatGrid
- ✅ Adapter table with re-sync buttons per adapter
- ✅ Config display panel and log viewer
- ❌ Missing domain grouping (currently a flat adapter table)
- ❌ Pipeline config editor not present
- ❌ Per-adapter re-poll lacks `Toast` feedback (hook exists via `useToast`)

**Implementation Tasks:**
1. Group adapters by domain using `Panel` per domain group
2. Use `Chip form="default" variant={healthColor}` for adapter status (replace raw `Badge`)
3. Add `Toast` feedback on re-poll success/error (the `useToast` hook already exists)
4. Add pipeline config UI using `Field`, `Select`, `TextInput` from Heimdall

---

## Shared Components to Build

### Version Pill
Small badge showing version number (v1, v2, v3…) with amber styling.

**Usage:** Sources table, source detail, chunk inspector, all domain views

**Implementation:** Use `Chip` from Heimdall with `form="version"`. **No custom component needed.**
```tsx
import { Chip } from '@tinkermonkey/heimdall-ui';
<Chip form="version">v3</Chip>
```

### HEAD Badge
Amber filled badge for the current version.

**Usage:** Version timelines, source detail header

**Implementation:** Use `Chip` with `variant="amber"` and `form="default"`. **No custom component needed.**
```tsx
<Chip variant="amber" form="default">HEAD</Chip>
```

### ID Tag
Neutral tag for identifiers (source IDs, connection strings, hashes).

**Usage:** Page headers, breadcrumbs, metadata panels

**Implementation:** Use `Chip` with `form="id-tag"`. **No custom component needed.**
```tsx
<Chip form="id-tag">localhost:8000</Chip>
<Chip form="id-tag">{sourceId.slice(0, 16)}…</Chip>
```

### Environment Indicator
Environment pill with colored dot (e.g., `chroma · ok`, `sqlite · ok`).

**Usage:** Statusbar, topbar, admin view

**Implementation:** Use `Chip` with `form="env"`. **No custom component needed.**
```tsx
<Chip form="env">chroma · ok</Chip>
```

### Status Chip
Colored inline status label (ok / running / warn / error).

**Usage:** Sources table STATE column, adapter cards, pipeline steps

**Implementation:** Use `Chip` with `variant` and `form="default"`. **No custom component needed.**
```tsx
<Chip variant="emerald" form="default">ok</Chip>
<Chip variant="amber" form="default">warn</Chip>
<Chip variant="rose" form="default">error</Chip>
<Chip variant="cyan" form="default">running</Chip>
```

### Segmented Control (vector / rerank / hybrid toggle)
⚠️ **NOT `TriState`** — `TriState` is a three-state checkbox, not a segmented control.

**Usage:** Search query mode toggle

**Implementation:** Use a row of `Button` components, tracking active state:
```tsx
{(['vector', 'rerank', 'hybrid'] as const).map(mode => (
  <Button
    key={mode}
    variant={queryMode === mode ? 'primary' : 'secondary'}
    size="sm"
    onClick={() => setQueryMode(mode)}
  >{mode}</Button>
))}
```

### Filter Dropdown
⚠️ **NOT Heimdall `Select`** — `Select` is a plain native `<select>` element. The design's `fd-trigger` pattern is a labeled button that reveals a flyout panel.

**Usage:** Search filter row, sources browser filter row

**Implementation:** Custom `FilterDropdown` component:
```tsx
// Renders a <button> trigger: label + selected value + chevronDown icon
// On click, shows a positioned popover with filter options
// Trigger uses Button variant="secondary" from Heimdall
// Popover uses --canvas-surface, --canvas-border, --radius-md tokens
```

### Domain Dot
6px colored circle indicating domain type.

**Usage:** Sidebar domain nav section, everywhere domains are referenced inline

**Implementation:** CSS-only using `--domain-*` tokens (no JS library):
```tsx
<span
  className="domain-dot"
  style={{ background: `rgb(var(--domain-${domain}))` }}
/>
// CSS: .domain-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
```

### Domain Color Bar
3px vertical bar on left edge of cards/rows showing domain color.

**Usage:** Sources table, search results, domain cards

**Implementation:** Inline style (no separate component needed):
```tsx
<div style={{
  width: 3,
  alignSelf: 'stretch',
  borderRadius: 2,
  background: `rgb(var(--domain-${domain}))`,
  flexShrink: 0,
}} />
```

### Mono Eyebrow
Uppercase mono section label (10–11px, 0.10em letter-spacing, muted).

**Usage:** Panel section headers, KV grid labels throughout

**Implementation:** Inline style (or `.eyebrow` CSS class):
```tsx
<span style={{
  fontSize: 10,
  fontFamily: 'JetBrains Mono, monospace',
  letterSpacing: '0.10em',
  textTransform: 'uppercase',
  color: 'rgb(var(--canvas-fg-3))',
}}>LAST 24 HOURS</span>
```

### Similarity Bar
Horizontal bar showing similarity score (0.0–1.0) with color coding.

**Usage:** Search results — already implemented as `ScoreBar` in `routes/search.tsx`. Standardize this pattern.

**Reference implementation in `routes/search.tsx`:**
```tsx
function ScoreBar({ score }: { score: number }) {
  const color = score >= 0.8 ? 'rgb(var(--status-ok))' : score >= 0.6 ? 'rgb(var(--status-amber))' : 'rgb(var(--canvas-fg-3))';
  return (
    <div style={{ width: 36, height: 4, background: 'rgb(var(--canvas-surface))', borderRadius: 2, overflow: 'hidden' }}>
      <div style={{ width: `${Math.round(score * 100)}%`, height: '100%', background: color }} />
    </div>
  );
}
```

### Lineage Rail
Horizontal provenance chain: pills with arrows between each step.

**Usage:** Chunk inspector, search result metadata

**Implementation:** Custom component using `Chip` + `Icon`:
```tsx
function LineageRail({ nodes }: { nodes: { label: string; icon?: IconName }[] }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
      {nodes.map((node, i) => (
        <React.Fragment key={i}>
          <Chip form="id-tag">{node.label}</Chip>
          {i < nodes.length - 1 && <Icon name="arrowRight" size={12} />}
        </React.Fragment>
      ))}
    </div>
  );
}
```

### Chunk Marker
Inline marker showing chunk boundary in markdown content.

**Usage:** Notes domain, markdown reader in chunked view

**Implementation:**
```tsx
<span style={{
  display: 'block',
  fontFamily: 'JetBrains Mono, monospace',
  fontSize: 10,
  color: 'rgb(var(--canvas-fg-4))',
  borderTop: '1px dashed rgb(var(--canvas-border))',
  paddingTop: 4,
  marginTop: 8,
}}>∙ chunk_01 · # Section · 7e3a91ff21…</span>
```

### Hash Display
Truncated SHA-256 hash with mono font and copy button.

**Usage:** Chunk inspector, source detail, search results

**Implementation:**
```tsx
function HashDisplay({ hash }: { hash: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <code style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
        {hash.slice(0, 12)}…
      </code>
      <button onClick={() => navigator.clipboard.writeText(hash)} aria-label="Copy hash">
        <Icon name="copy" size={12} />
      </button>
    </span>
  );
}
```

### Version Timeline Item
Card in version history sidebar showing version headline, diff stats, timestamp.

**Usage:** Source detail

**Implementation:** Custom card using Heimdall tokens:
```tsx
// Clickable card with:
// - <Chip form="version">v3</Chip>  for version label
// - <Chip variant="amber" form="default">HEAD</Chip>  if current version
// - Headline text (canvas-fg-1)
// - Summary text (canvas-fg-3, smaller)
// - Stats: +{adds} −{removes} ={keeps} (emerald/rose/neutral)
// - Relative timestamp (canvas-fg-4)
// Selected state: shell-surface-2 background
```

### Three-Pane Layout (Notes, Messages)
⚠️ **`SplitPane` only supports two panes.** For three-pane views, nest two `SplitPane` components:
```tsx
<SplitPane
  direction="horizontal"
  initialSplitPercent={22}
  minSize={180}
  maxSize={360}
  first={<FileTreePanel />}
  second={
    <SplitPane
      direction="horizontal"
      initialSplitPercent={70}
      minSize={300}
      maxSize={800}
      first={<MarkdownReaderPanel />}
      second={<OutlinePanel />}
    />
  }
/>
```

---

## CSS Architecture Updates

### Current Issues
1. `/ui/src/index.css` overrides Heimdall tokens (cyan accent instead of amber)
2. Custom domain color definitions don't use design system
3. Mixing Tailwind utility classes with custom CSS

### Fixes Needed

1. **Update `/ui/src/index.css`:**

The Heimdall npm package defines shell/canvas/accent/status tokens. App-level domain color tokens (`--domain-*`) are NOT defined by the package — they are app-level tokens declared in `index.css`. The `designTokens.ts` file references them as `var(--domain-notes)` etc.

```css
/* REMOVE the cyan accent override (currently at top of index.css): */
/* --accent-primary: 99 102 241;  ← DELETE THIS */

/* Domain colors — token names must match designTokens.ts (--domain-* prefix) */
/* Values are space-separated RGB channels for rgb(var(--domain-X) / 0.5) usage */
:root {
  --domain-notes: 129 140 248;     /* indigo  #818CF8 */
  --domain-messages: 34 211 238;   /* cyan    #22D3EE */
  --domain-events: 245 158 11;     /* amber   #F59E0B */
  --domain-tasks: 16 185 129;      /* emerald #10B981 */
  --domain-documents: 148 163 184; /* slate   #94A3B8 */
  --domain-people: 192 132 252;    /* violet  #C084FC */
  --domain-location: 20 184 166;   /* teal    #14B8A6 */
  --domain-music: 244 114 182;     /* pink    #F472B6 */
  --domain-health: 248 113 113;    /* coral   #F87171 */
}
```

⚠️ Use `--domain-*` prefix everywhere — it's what `designTokens.ts` and all route files already reference via `getDomainColor()`. Do **NOT** switch to `--dom-*` — that prefix is only in the design reference CSS, not the npm package or app code.

2. **Create `/ui/src/styles/domain.css`:**
Add CSS-only layout primitives for domain color bars and dots:
```css
/* Domain color bar — 3px left edge bar on cards */
.domain-bar {
  width: 3px;
  align-self: stretch;
  border-radius: 2px;
  flex-shrink: 0;
}

/* Domain dot — 6px circle */
.domain-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* Chunk marker — inline chunk boundary in markdown */
.chunk-mark {
  display: block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.08em;
  color: rgb(var(--canvas-fg-4));
  border-top: 1px dashed rgb(var(--canvas-border));
  padding-top: 4px;
  margin-top: 8px;
}

/* Mono eyebrow label — uppercase section headers */
.eyebrow {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: rgb(var(--canvas-fg-3));
}
.eyebrow-shell {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: rgb(var(--shell-fg-3));
}
```

All other custom styles (hash-diff-grid, version-item, lineage-rail, etc.) are component-scoped — use CSS modules (`.module.css`) or inline styles via Heimdall tokens. Do NOT create a large monolithic design-refresh CSS that duplicates the design reference file.

3. **Consolidate Tailwind Usage:**
- Prefer Heimdall component props over Tailwind utility classes where possible
- Prefer `style={{ … }}` using `rgb(var(--token))` over arbitrary Tailwind color values like `text-indigo-400`
- Tailwind layout utilities (`flex`, `gap-2`, `items-center`, `min-w-0`, etc.) are fine alongside design system components
- Remove all hardcoded hex colors; replace with token references

---

## API Expansion Requirements

### New Endpoints Needed

1. **Pipeline Status**
   - `GET /admin/pipelines` → List of active pipelines with current step
   - Response: `{ pipelines: [{ adapter_id, status, step, detail, version }] }`

2. **Activity Feed**
   - `GET /stats/activity?limit=20` → Structured activity log
   - Response: `{ events: [{ type, timestamp, headline, metadata, tag }] }`

3. **Source Detail**
   - `GET /sources/{source_id}/versions` → Full version list with stats
   - Response: `{ versions: [{ version_number, created_at, headline, summary, added_count, removed_count, kept_count }] }`

4. **Version Diff**
   - `GET /sources/{source_id}/versions/{from}/diff/{to}` → Hash-set diff
   - Response: `{ added: [{ hash, position, section }], removed: [...], kept: [...] }`
   - `GET /sources/{source_id}/versions/{version}/content` → Raw content for side-by-side

5. **Chunk Provenance**
   - `GET /chunks/{hash}/provenance` → Full lineage
   - Response: `{ adapter_id, adapter_version, normalizer_version, source_id, source_version, domain, chunk_position, section, embedding_model, parent_hash, created_at }`
   - `GET /chunks/{hash}/ancestors` → Version chain
   - Response: `{ ancestors: [{ hash, version_number, created_at }] }`
   - `GET /chunks/{hash}/embedding` → Vector data (optional, for debug)

6. **Cross-References**
   - `GET /sources/{source_id}/cross-refs` → References to other sources
   - Response: `{ refs: [{ target_source_id, ref_type, section }] }`

7. **Outline Extraction**
   - `GET /sources/{source_id}/outline` → Heading structure (notes domain)
   - Response: `{ outline: [{ level, text, chunk_hash }] }`

8. **Thread Metadata**
   - `GET /sources/{source_id}/thread` → Message thread info
   - Response: `{ participants: [...], message_count, date_range }`

9. **Task Lifecycle**
   - `GET /sources/{source_id}/lifecycle` → State transition history
   - Response: `{ transitions: [{ from_state, to_state, timestamp, version_number }] }`

10. **People Relationships**
    - `GET /people/{person_id}/relationships` → Connections
    - Response: `{ connections: [{ person_id, relationship_type, strength }] }`
    - `GET /people/{person_id}/activity` → Interaction timeline
    - Response: `{ events: [{ type, timestamp, source_id, summary }] }`

11. **Music Stats**
    - `GET /music/play-history?from=&to=` → Listening timeline
    - Response: `{ plays: [{ timestamp, track, artist, album }] }`
    - `GET /music/stats?period=30d` → Aggregated data
    - Response: `{ top_artists: [...], top_genres: [...], top_decades: [...] }`

12. **Search Enhancement**
    - Add `include_provenance=true` param to `POST /query`
    - Return parent_hash, adapter_id, normalizer_version in results

---

## Implementation Phases

### Phase 1: Design System Alignment (Week 1)
**Goal:** Fix token usage, ensure consistent Heimdall component usage

- [ ] Update `/ui/src/index.css` with amber accent and correct domain colors
- [ ] Create `/ui/src/components/design-refresh.css` with shared patterns
- [ ] Audit all routes for Heimdall component usage
- [ ] Replace custom buttons/inputs with Heimdall equivalents
- [ ] Standardize Panel, Modal, TabBar usage

**Deliverable:** All existing screens use Heimdall components consistently

### Phase 2: Shared Components (Week 2)
**Goal:** Build reusable design refresh patterns

- [ ] Delete `components/shared/DomainBadge.tsx` (replaced by `Chip form="id-tag"` + domain color)
- [ ] Build `FilterDropdown` component (custom flyout, NOT Heimdall Select)
- [ ] Build `LineageRail` component (uses `Chip form="id-tag"` + `Icon name="arrowRight"`)
- [ ] Build `DomainNavSection` (custom nav section with `.domain-dot` spans alongside `NavItem`)
- [ ] Create `ui/src/styles/domain.css` with `.domain-bar`, `.domain-dot`, `.chunk-mark`, `.eyebrow`
- [ ] Build `HashDisplay` component (truncated hash + copy button)
- [ ] Standardize `ScoreBar` component (move to `components/shared/ScoreBar.tsx`)

**Deliverable:** Shared component library for design refresh

### Phase 3: API Expansion (Week 2–3)
**Goal:** Add backend support for new UI features

- [ ] Implement pipeline status endpoint
- [ ] Implement activity feed endpoint
- [ ] Implement source versions endpoint
- [ ] Implement version diff endpoint
- [ ] Implement chunk provenance endpoint
- [ ] Implement search provenance param
- [ ] Add other domain-specific endpoints as needed

**Deliverable:** Backend API supports all design refresh features

### Phase 4: Overview/Dashboard Refresh (Week 3)
**Goal:** Rebuild dashboard to match design

- [ ] Rebuild stat grid with StatGrid component
- [ ] Create domain breakdown panel with adapters/chunks
- [ ] Create pipeline activity panel
- [ ] Enhance activity feed with icons and formatting
- [ ] Add page header with health chip

**Deliverable:** Dashboard matches design spec

### Phase 5: Search Refresh (Week 4)
**Goal:** Implement hero search and rich result cards

- [ ] Create SearchHeroCard with filter row
- [ ] Create SearchResultCard with similarity bar and metadata
- [ ] Add facets sidebar
- [ ] Add sort controls
- [ ] Wire up reranker toggle

**Deliverable:** Search matches design spec

### Phase 6: Sources Browser Refresh (Week 4)
**Goal:** Enhanced table with filters and version pills

- [ ] Add filter dropdown row
- [ ] Update table columns with domain bars, version pills, status chips
- [ ] Add active filter count indicator
- [ ] Enhance pagination footer

**Deliverable:** Sources browser matches design spec

### Phase 7: Source Detail (NEW) (Week 5)
**Goal:** Build version timeline and diff views

- [ ] Create source detail route
- [ ] Build version timeline component
- [ ] Build hash-set diff view
- [ ] Build content diff view
- [ ] Add version selectors and mode toggle

**Deliverable:** Source detail screen functional

### Phase 8: Chunk Inspector (NEW) (Week 5–6)
**Goal:** Build provenance and lineage views

- [ ] Create chunk inspector route
- [ ] Build lineage rail component
- [ ] Build context header + content panels
- [ ] Build version chain panel
- [ ] Build metadata panel

**Deliverable:** Chunk inspector screen functional

### Phase 9: Domain View Refinements (Week 6–7)
**Goal:** Update all domain views to match design patterns

- [ ] Notes: Three-pane layout with file tree and chunk markers
- [ ] Messages: Three-pane with thread list and metadata
- [ ] Events: Enhanced calendar with Heimdall components
- [ ] Tasks: Kanban board with lifecycle timeline
- [ ] Documents: Refined tree and preview
- [ ] Health: Stat cards and heatmap
- [ ] Location: Enhanced map and timeline
- [ ] People: Relationship graph and activity
- [ ] Music: Album grid and stats

**Deliverable:** All domain views match design patterns

### Phase 10: Admin/Adapters Refresh (Week 7)
**Goal:** Enhanced adapter management UI

- [ ] Create adapter cards with status and controls
- [ ] Add per-adapter re-poll buttons
- [ ] Add pipeline configuration UI

**Deliverable:** Admin screen matches design spec

### Phase 11: Polish & Testing (Week 8)
**Goal:** Refinement and edge case handling

- [ ] Cross-browser testing
- [ ] Responsive adjustments (if needed)
- [ ] Animation polish
- [ ] Performance optimization
- [ ] Documentation updates

**Deliverable:** Production-ready UI refresh

---

## Success Criteria

1. **Design System Compliance**: 100% of components use Heimdall design system where applicable
2. **Visual Consistency**: All screens match design refresh specs with <5% deviation
3. **Token Alignment**: Amber accent used throughout, correct domain colors, proper spacing/radius
4. **Functionality**: All new features (version diff, chunk provenance, lineage rails) working
5. **Performance**: No regressions in load time or interaction responsiveness
6. **API Coverage**: All new endpoints implemented and tested
7. **Maintainability**: Clear component structure, reusable patterns, documented deviations

---

## Risk Assessment

### High Risk
- **API expansion complexity**: Version diff computation, provenance tracking may require backend refactoring
  - *Mitigation*: Implement endpoint stubs early, iterate on data structure
- **Performance of new views**: Lineage rails, diff views may be slow for large datasets
  - *Mitigation*: Implement pagination, lazy loading, virtualization where needed

### Medium Risk
- **Scope creep**: Design refresh is comprehensive, easy to over-engineer
  - *Mitigation*: Stick to design specs, defer enhancements to later phases
- **Heimdall component limitations**: Design system may not have all needed variants
  - *Mitigation*: Extend Heimdall components with custom CSS, document gaps for upstream contribution

### Low Risk
- **Design token conflicts**: Overriding Heimdall tokens may cause inconsistencies
  - *Mitigation*: Prefer Heimdall tokens, only override when design spec explicitly differs

---

## Appendix: Component Mapping

### Heimdall Components → Design Patterns

| Design Pattern | Heimdall Component | Notes |
|---|---|---|
| Stat tiles (4-up) | `StatTile` + `StatGrid` | Use directly; `delta` prop supports up/down indicators |
| Domain cards (overview) | `Panel` + custom content | Panel for card structure, custom for domain bar + adapter chips |
| Activity feed | Custom list | No direct equivalent; build with `Panel` wrapper |
| Search hero card | `Panel` + `TextInput` + `FilterDropdown` (custom) | `TextInput mono` for query; Heimdall `Select` is native—use custom filter dropdowns |
| Result cards | Custom card component | Too specific for `Panel`; inline styles with design tokens |
| Filter dropdowns (fd-trigger) | Custom `FilterDropdown` component | Heimdall `Select` is a native `<select>`, not a flyout; build custom |
| Query mode toggle (vector/rerank/hybrid) | `Button` group | ⚠️ NOT `TriState`; use row of `Button variant="secondary"` tracking active state |
| Data table | `Table` | Use directly; `render` fn per column supports chips, bars, pills |
| **Version pills** | `Chip form="version"` | ✅ Built into Chip; `<Chip form="version">v3</Chip>` |
| **ID tags** | `Chip form="id-tag"` | ✅ Built into Chip; `<Chip form="id-tag">{id}</Chip>` |
| **Env indicators** | `Chip form="env"` | ✅ Built into Chip; `<Chip form="env">chroma · ok</Chip>` |
| **Status labels** | `Chip variant={color} form="default"` | ✅ Chip has colored dot; emerald/amber/rose/cyan/violet/neutral |
| Domain dots | CSS-only (`.domain-dot` with `--domain-*` tokens) | Inline style `background: rgb(var(--domain-notes))` |
| Domain color bars | Inline style | `width: 3px`, `background: rgb(var(--domain-X))` |
| HEAD badge | `Chip variant="amber" form="default"` | Amber fills correctly |
| Lineage rail | Custom `LineageRail` | Uses `Chip form="id-tag"` + `Icon name="arrowRight"` |
| Three-pane layouts | Nested `SplitPane` | `SplitPane` is binary; nest two for 3 panes |
| Sidebar nav | `Sidebar` | Domain dots need custom rendering outside Sidebar items |
| Workspace chip | `Chip form="id-tag"` in `Topbar` children | Goes in `Topbar children` prop |
| Env pill in topbar | `Chip form="env"` in `Topbar` children | Goes in `Topbar children` prop |
| Tabs | `TabBar` | Use directly |
| Buttons | `Button` | Variants: primary/secondary/ghost/danger/link |
| Status badge (larger block) | `StatusBadge` | Block-level colored dot + label |
| Modals | `Modal`, `ConfirmDialog` | `title`/`subtitle` are strings only; custom header goes in `children` |
| Drawers | `Drawer position="right"` | Use for ChunkInspector, OutlinePanel overlay |
| Toasts | `Toast` | Already used via `useToast` hook |
| Command palette | `CommandPalette` | Trigger button goes in `Topbar children` |

### Custom Components Needed

These are genuinely custom — no Heimdall equivalent exists:

1. **FilterDropdown** — Button-triggered flyout panel for filter rows. Trigger: `Button variant="secondary"` + `Icon name="chevronDown"`. Popover: positioned div using `--canvas-surface` + `--canvas-border` tokens.
2. **LineageRail** — Horizontal provenance chain. Use `Chip form="id-tag"` nodes + `Icon name="arrowRight"` separators.
3. **SearchResultCard** — Rich result card (domain bar + path + snippet + score + metadata). Too specific for `Panel`.
4. **HashSetDiffView** — Three-column diff grid (Added / Retired / Kept). Each column scrollable with hash + position items.
5. **ContentDiffView** — Side-by-side markdown diff with line +/- highlighting.
6. **VersionTimelineItem** — Clickable timeline card. Uses `Chip form="version"` for label, `Chip variant="amber" form="default"` for HEAD, emerald/rose/neutral for stats.
7. **PipelineActivityPanel** — Mini-pipeline progress visualization (6 steps). Uses `StatusBadge` and `Chip` for step indicators.
8. **FileTreePanel** — Collapsible tree navigation for Notes domain. Uses `Icon name="chevronRight"/"chevronDown"` for expand/collapse.
9. **KanbanBoard** — Three-column task board (To Do / In Progress / Done). Uses `Panel` for each column.
10. **RelationshipGraph** — SVG-based connection graph for People domain.
11. **HeatmapCalendar** — Calendar grid with intensity overlay for Health/Location domains.
12. **DomainNavSection** — Custom sidebar section with domain dots + chunk counts. Required because `Sidebar` items only accept `icon: IconName` — not custom dot indicators. Render with `NavItem` components plus `.domain-dot` spans.

**NOT in custom list** (use Heimdall `Chip` forms instead):
- ~~VersionPill~~ → `<Chip form="version">v3</Chip>`
- ~~IDTag~~ → `<Chip form="id-tag">{id}</Chip>`
- ~~EnvPill~~ → `<Chip form="env">chroma · ok</Chip>`
- ~~StatusChip~~ → `<Chip variant="emerald" form="default">ok</Chip>`
- ~~DomainBadge~~ → delete `components/shared/DomainBadge.tsx`; use `Chip form="id-tag"` + domain color inline style

---

## Conclusion

This UX refresh represents a significant upgrade to the Context Library interface, bringing it into full alignment with the Heimdall Design System while introducing sophisticated versioning workflows that showcase the system's content-addressed, hash-based architecture. The phased implementation approach ensures steady progress while maintaining system stability. The focus on maximizing design system component re-use will yield a more maintainable, consistent, and visually cohesive application.

**Next Steps:**
1. Review and approve this plan
2. Begin Phase 1: Design System Alignment
3. Set up weekly progress check-ins
4. Track completion against phase deliverables
