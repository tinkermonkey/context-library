# Entity Linking

How person chunks get connected to the messages, events, tasks, and documents that mention them, and where that connection silently fails to happen.

Implementation: `src/context_library/core/entity_linker.py`. Normalization: `src/context_library/core/identifier_normalizer.py`. See [normalization-contract.md](./normalization-contract.md) for the phone/email format contract this pass depends on.

---

## Why this exists

Chunks in the `messages`, `events`, `tasks`, and `documents` domains carry a sender/recipient/attendee/collaborator/author as a raw string (an email address or phone number) in their `domain_metadata`. Chunks in the `people` domain carry the same identifiers, structured, on a `PeopleMetadata` contact record. Nothing about the pipeline (`fetch → normalize → diff → chunk → embed → store`) connects these two views of the same identifier — a message from `alice@example.com` and a contact whose `emails` includes `alice@example.com` are two unrelated rows until something joins them.

`EntityLinker` is that join. It runs as a **post-pipeline pass**, not as part of `IngestionPipeline` itself: it is triggered explicitly after a People-domain ingestion completes (see `_run_entity_linking` in `server/routes/ingest.py`), because only People ingestion can introduce new identifiers to match against everything else already stored.

## Algorithm

`EntityLinker.run()`, in order:

1. **Clean up stale links first.** Delete `entity_links` rows whose `source_chunk_hash` is a retired person chunk, and rows whose `target_chunk_hash` is any retired chunk. Both deletes use `DELETE ... WHERE NOT EXISTS` against the live `chunks` table (not a read-then-delete) so a concurrent ingestion can't un-retire a chunk in the window between the check and the delete. This runs unconditionally, even if step 2 finds zero person chunks — otherwise a fully-retired People source would leave orphaned links behind forever.
2. **Fetch active person chunks**, paginated (`page_size=10000`) via `DocumentStore.list_chunks(domain=Domain.PEOPLE)`. Each page is processed and discarded before the next is fetched, so memory use is bounded regardless of contact count.
3. **Per person chunk, extract identifiers** from `chunk.domain_metadata` (the serialized `PeopleMetadata`): every entry in `emails` and every entry in `phones`, normalized (see below) and deduplicated into a single sorted list. A contact with no emails and no phones — or where every value normalizes to empty string — is skipped with no links attempted.
4. **Query other domains for those identifiers.** For each person chunk's identifier set, `DocumentStore.query_chunks_by_identifiers()` runs one SQL query against `chunks.domain_metadata` covering every non-people chunk at its **current source version** that isn't retired. See [JSON paths queried](#json-paths-queried-per-domain) below for exactly which fields.
5. **Write `entity_links` rows** for every `(person_chunk, matched_chunk)` pair, `link_type='person_appearance'`, `confidence=1.0` (confidence is not currently modulated — a match is binary). Writes are `INSERT OR IGNORE`, so re-running the pass over unchanged data is a no-op; the `UNIQUE(source_chunk_hash, target_chunk_hash, link_type)` constraint is what makes the pass idempotent and safe to re-trigger on every People ingestion rather than only on the first one.

A failure processing one person chunk (bad `domain_metadata` shape, SQL error, etc.) is caught, logged, and counted in the returned `total_chunks_failed` — it does not abort the page or the run. A failure in step 1 (cleanup) raises `EntityLinkingError` and aborts the whole pass, since a partially-cleaned-up state is worse than not running at all.

Directionality: links are always written `source_chunk_hash=<person chunk>`, `target_chunk_hash=<matched chunk>`. `entity_links` has no reverse rows — traversal from either side is a query concern (see [Query patterns](#query-patterns)), not a storage concern.

## JSON paths queried per domain

`_find_matching_chunks()` hardcodes two field lists and hands them to `query_chunks_by_identifiers()`:

```python
scalar_fields = ["sender", "host", "author"]
array_fields = ["recipients", "invitees", "collaborators"]
```

Each scalar field is compared with `json_extract(domain_metadata, '$.<field>')`; each array field is walked with `json_each(domain_metadata, '$.<field>')`. Both are run through `normalize_email_sql()` / `normalize_phone_sql()` before comparison. The fields map onto the domain metadata models (`storage/models.py`) as follows:

| Field | Kind | Metadata model | Populated by |
|---|---|---|---|
| `sender` | scalar | `MessageMetadata.sender` | Messages (email, iMessage) |
| `host` | scalar | `EventMetadata.host` | Events — the organizer (CalDAV `ORGANIZER`, Apple Calendar organizer) |
| `author` | scalar | `DocumentMetadata.author` | Documents (filesystem, rich-fs) |
| `recipients` | array | `MessageMetadata.recipients` | Messages |
| `invitees` | array | `EventMetadata.invitees` | Events — this **is** the calendar attendee list (CalDAV `ATTENDEE`, Apple Calendar `attendees`, minus the organizer) |
| `collaborators` | array | `TaskMetadata.collaborators` | Tasks (Apple Reminders shared lists) |

Calendar attendees are matched today — via `invitees`, not a field literally named `attendees`. This is easy to miss when scanning `_find_matching_chunks()` for the string `"attendees"`, since the wire-format key from adapters (`caldav.py`, `apple_calendar.py`) is `attendees`/`ATTENDEE` but the field is renamed to `invitees` when it lands in `EventMetadata`. Anyone adding a new event-like adapter must populate `EventMetadata.invitees`/`host`, not invent a parallel `attendees` field, or the linker will silently never see it (see [Failure modes](#failure-modes)).

**Domains with no queried fields at all:** `health`, `notes`, and `location` have no metadata field in either list — `HealthMetadata`, `LocationMetadata`, and the notes domain carry no sender/participant identifier. Chunks in these domains can never receive an inbound `person_appearance` link, by design (there is no "sender" of a sleep summary), not by a match failing.

The `people` domain itself is always excluded (`exclude_domain=Domain.PEOPLE`) — a contact never links to another contact through this pass.

## Normalization applied before matching

Both sides of the comparison — the identifier extracted from `PeopleMetadata` and the value pulled out of the target chunk's `domain_metadata` via `json_extract`/`json_each` — are run through the *same* two functions, so a mismatch can only come from the raw input already differing (see [normalization-contract.md](./normalization-contract.md)):

- **Email:** `normalize_email()` — strip, lowercase. No structural validation.
- **Phone:** `normalize_phone()` — strip a trailing extension (`ext.`, `x`, `extension` + digits), drop everything but digits and a leading `+`, and if there was no leading `+`, assume US and prepend `+1` (stripping any leading `0` first).

The Python-side functions (`identifier_normalizer.py`) and the SQL-side functions (`normalize_email_sql`/`normalize_phone_sql`, registered in `DocumentStore._make_connection()`) are the *same* Python code — the SQL functions just wrap the Python ones via `sqlite3.Connection.create_function`. There is one normalization implementation, not two that need to be kept in sync.

## Failure modes

These produce **no error and no log line above `debug`** — from the caller's perspective, a person simply has fewer links than expected. This is the sharp edge of the whole pass: matching is silent by design (step 4 is just "0 rows found"), so miscounts look identical to "this person genuinely doesn't appear anywhere."

- **Non-US numbers entered without a country code.** `normalize_phone("020 7946 0958")` (a UK number, national format) yields `+2079460958` — treated as if it were an oddly-shaped US number, not the intended `+442079460958`. This will never collide with the correctly-`+44`-prefixed version of the same number, so a UK contact whose messages use national format and whose contact card uses `+44` format will not link.
- **Leading zero stripped unconditionally.** Any digit string without a `+` has leading zeros stripped before the `+1` is prepended (`"0555 123 4567"` → `+15551234567`). This is correct for the specific case the code targets (a UK-style leading trunk zero misapplied to a US number) but means a `+1` number that legitimately starts counting from `0` after normalization elsewhere would collapse into a different number.
- **Two different local numbers under different country contexts.** Because numbers without `+` are always forced to `+1`, a `+1` contact number and a same-digit-sequence international number typed without its country code will incorrectly compare equal (or a genuinely different number will incorrectly compare unequal) depending on which side happened to include `+`. `normalize_phone`'s own docstring flags this as a known limitation, not a bug that's been fixed.
- **New adapter, wrong metadata field name.** If a new domain or adapter puts an identifier in a field not in `scalar_fields`/`array_fields` (e.g. a hypothetical chat adapter that uses `participants` instead of `recipients`), it is invisible to the linker with no warning at ingestion or link time. This has already happened once conceptually with `attendees` vs. `invitees` (see above) — the field got renamed at the metadata-model boundary, not at the adapter boundary, so the linker's hardcoded list stayed correct, but a naive read of an adapter's raw JSON would suggest otherwise.
- **`extended_fields` is never scanned.** `PeopleMetadata.extended_fields` (raw contact data — alternate phone/email labels, related names) is explicitly excluded from `_extract_identifiers()`, which only reads the top-level `emails`/`phones` tuples. A phone number that only exists in `extended_fields` (e.g. an adapter that puts a work fax number there instead of in `phones`) is never a candidate for matching.
- **Health, Notes, and Location chunks are structurally unlinkable** — see the domain table above. This isn't a bug, but it is a common "why isn't X linked" support question.
- **Whole-run failure only comes from cleanup.** A malformed `domain_metadata` on one person chunk is caught per-chunk (counted in `total_chunks_failed`, logged at `warning`); a failure in `_cleanup_retired_chunks_links()` raises `EntityLinkingError` and aborts the entire run, leaving that ingestion's `entity_linking_status` as `"failed"` (see `server/routes/ingest.py`).

## Query patterns

There is currently no HTTP endpoint over `entity_links` — it's a storage-layer concept only, queried directly against `DocumentStore` or SQLite. The intended patterns:

### From code: bidirectional traversal

```python
# All chunks linked to this one, either direction, any link type
document_store.get_linked_chunks(chunk_hash)

# Scoped to a specific link type
document_store.get_linked_chunks(chunk_hash, link_type="person_appearance")
```

`get_linked_chunks()` unions a source-side and target-side query, so it works the same whether `chunk_hash` is a person chunk or a message/event/task/document chunk — callers don't need to know which side of the link they're holding.

### Direct SQL: "who appears in this message/event/task?"

```sql
SELECT p.chunk_hash, p.content, p.domain_metadata
FROM entity_links el
JOIN chunks p ON p.chunk_hash = el.source_chunk_hash
WHERE el.target_chunk_hash = :target_chunk_hash
  AND el.link_type = 'person_appearance'
  AND p.retired_at IS NULL;
```

### Direct SQL: "everything a given person appears in, by domain"

```sql
SELECT c.domain, COUNT(*) AS mentions
FROM entity_links el
JOIN chunks c ON c.chunk_hash = el.target_chunk_hash
WHERE el.source_chunk_hash = :person_chunk_hash
  AND c.retired_at IS NULL
GROUP BY c.domain
ORDER BY mentions DESC;
```

### Direct SQL: coverage / audit — contacts with zero links

Useful for catching the normalization mismatches above in aggregate, rather than one contact at a time:

```sql
SELECT p.chunk_hash, p.domain_metadata
FROM chunks p
WHERE p.domain = 'people'
  AND p.retired_at IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM entity_links el WHERE el.source_chunk_hash = p.chunk_hash
  );
```

A large or growing result set from this query, for contacts known to have messages/events on file, is the practical signal that a normalization mismatch (see [Failure modes](#failure-modes)) is actively costing links — it's the only way to notice, since individual failures don't surface anywhere else.
