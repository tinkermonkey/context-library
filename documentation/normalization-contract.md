# Identifier Normalization Contract

The phone/email format that [context-helpers](../../context-helpers) emits and the format `context_library`'s entity linker expects are **not the same operation**, and nothing enforces that they converge. This document is the contract that should hold across the boundary, what actually happens today on each side, and where the gap is.

See [entity-linking.md](./entity-linking.md) for how this normalization is used downstream.

---

## The contract

For entity linking to work, two independently-produced values must normalize to the *same string*:

1. A phone/email as it appears in a **contact record** (`PeopleMetadata.emails` / `.phones`, sourced from Apple Contacts via context-helpers, or a vCard/CardDAV import).
2. A phone/email as it appears in **content the person is associated with** — an email `sender`, an iMessage handle, a calendar `invitees` entry, a task `collaborators` entry.

The canonical comparison format `context_library` normalizes both sides to at query time is:

- **Email:** lowercase, leading/trailing whitespace stripped. No further validation (a syntactically invalid email still normalizes and can still match, since the linker never rejects an identifier — it only compares strings).
- **Phone:** digits only, with a leading `+` preserved if present in the input; if absent, `+1` is prepended (after stripping a leading `0`). This is **E.164-shaped but not E.164** — true E.164 requires the country code to be known, and this format assumes US (`+1`) for any number typed without one. It is only correct for genuinely-US numbers typed in national format; see the limitations called out in `identifier_normalizer.py` and in [entity-linking.md](./entity-linking.md#failure-modes).

Both the Python implementation (`normalize_email`/`normalize_phone` in `core/identifier_normalizer.py`) and the SQL-side implementation (`normalize_email_sql`/`normalize_phone_sql` in `storage/document_store.py`) are the same code — the SQL functions are registered via `sqlite3.Connection.create_function` and call straight through. There's exactly one normalization implementation inside `context_library`.

**The contract only holds if both producers emit something this normalization can reconcile.** Two raw strings that describe the same phone number but can't be reduced to the same digit sequence by "strip formatting, assume `+1` if no `+`" will never match, no matter how many times the pass re-runs.

## What context-helpers actually emits today

context-helpers does **no phone normalization**. The Contacts collector (`collectors/contacts/collector.py`) pulls `phones`/`emails` straight out of `Application('Contacts').people` via JXA and passes the strings through verbatim:

```javascript
phones: phones || [],   // whatever Contacts.app has stored, unmodified
```

That means a contact's phone number is whatever the user (or an import) typed into Contacts.app — `"(555) 123-4567"`, `"555.123.4567"`, `"+1 555 123 4567"`, a UK number as `"020 7946 0958"` or `"+44 20 7946 0958"`, or anything else Contacts.app accepts. There is no canonicalization step, no `phonenumbers`-style library in the collector, and no schema constraint forcing a shape.

Emails from the same collector are similarly untouched — whatever string Contacts.app has for an email field, case included.

On the message side, iMessage handle IDs (`collectors/imessage/collector.py`, reading `handle.id` from `chat.db`) are **usually** already close to E.164 for phone-registered handles, because Messages.app itself normalizes handles internally — but this is an artifact of how Apple's Messages database stores handles, not a guarantee context-helpers makes or checks. context-helpers has no test or assertion pinning this format.

## What context_library does about it

`context_library` treats normalization as **its own responsibility, applied at write/query boundaries, not trusted from either producer**:

- `EntityLinker._extract_identifiers()` normalizes every email/phone pulled from `PeopleMetadata` before using it as a query parameter.
- `DocumentStore.query_chunks_by_identifiers()` normalizes both the query parameters *and* every value read out of `domain_metadata` (via the SQL functions) before comparing.

This is why entity linking works *at all* today despite context-helpers doing nothing — `context_library` is the only place normalization happens, and it happens symmetrically on both sides of every comparison.

## The gap

Because the "assume `+1` if no `+`" rule in `normalize_phone()` is the *only* thing standing in for real E.164 conversion, it produces silent link failures whenever:

- A contact's phone is stored in Contacts.app in a non-US national format (no `+`, no leading `1`) for a non-US number. Normalization forces it to `+1<digits>`, which will never equal the correctly-`+`-prefixed international form appearing elsewhere.
- The same underlying number appears in two different "no country code, guess `+1`" shapes that happen to collapse to different digit strings (e.g. one side includes a leading trunk `0` that the other already stripped).

There is no retry, no fuzzy matching, and no logging when this happens — see [entity-linking.md § Failure modes](./entity-linking.md#failure-modes) for the audit query that surfaces it indirectly.

**Recommended contract going forward**, if this gap is to be closed rather than just documented: context-helpers should normalize phone numbers to true E.164 at collection time (e.g. via the `phonenumbers` library, using the device's region as the default country hint instead of always assuming `+1`), and `context_library`'s `normalize_phone()` should become a passthrough/validation step rather than the sole source of canonicalization. Until that lands, `context_library`'s "digits + assume-`+1`" normalization is the entire normalization contract in effect, and it is US-centric by construction.
