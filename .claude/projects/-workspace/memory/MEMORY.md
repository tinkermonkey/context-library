# Issue #328: Schema / Data Integrity - entity_links FK Constraints

## Problem
The `entity_links` table was missing foreign key constraints required by spec (FR-2.2):
- `source_chunk_hash` and `target_chunk_hash` should reference `chunks(chunk_hash)`
- Without FK constraints, orphaned entity_links could accumulate when chunks are retired/deleted
- Silent failures in `write_entity_links` via `INSERT OR IGNORE` could hide data integrity issues

## Solution Implemented
1. **Added UNIQUE constraint on chunk_hash in chunks table** (schema.sql:52, document_store.py:567)
   - Makes chunk_hash a valid foreign key target
   - Aligns with content-addressed design: same content = same hash = single row
   - While chunks exist in (chunk_hash, source_id, source_version) composite PK, the UNIQUE on chunk_hash ensures each distinct content appears once

2. **Added FK constraints to entity_links** (schema.sql:100-101, document_store.py:615-616)
   - `source_chunk_hash REFERENCES chunks(chunk_hash)`
   - `target_chunk_hash REFERENCES chunks(chunk_hash)`
   - Enforces database-level referential integrity
   - Prevents insertion of entity_links with non-existent chunk_hashes
   - Protects against orphaned links

3. **Updated migration code** (document_store.py:_migrate_v3_to_v4)
   - Includes UNIQUE constraint on chunk_hash
   - Creates entity_links with proper FK constraints

## Key Insight
The architecture supports cross-source deduplication (same content hash in different sources), but the identity is still the chunk_hash - it's just stored multiple times for provenance. Making chunk_hash globally unique is correct for the content-addressed semantics while the composite PK preserves source/version lineage.

## Test Results
- All 150 document_store tests pass ✓
- All 23 entity_linker tests pass ✓
- All 4 people integration tests pass ✓
- All 443 critical storage/entity_linker/integration tests pass ✓
- No test regressions
