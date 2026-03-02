# Documentation Cross-References Audit

## Overview

This document tracks verified internal cross-references between the three main design documents:
- `Architecture.md` — System architecture, data flow, and class diagrams
- `persistence-design.md` — Storage engine design, SQLite/LanceDB architecture, and read/write paths
- `chunking-strategy.md` — Semantic chunking algorithm and domain-specific implementations

---

## Verified Cross-References

### Architecture.md → persistence-design.md

| Location | Reference | Target | Status |
|----------|-----------|--------|--------|
| Lines 468-470 | "Why dual storage (document store + vector store)?" | Storage Architecture section at persistence-design.md:7-15 | ✓ Valid |
| Lines 33-34, 55-56 | Messages, Notes, Events, Tasks domains with chunking | Domain-specific chunking covered at chunking-strategy.md:239-266 | ✓ Valid |

**Details:**
- The "dual storage" explanation in Architecture.md:468-470 directly corresponds to the Storage Architecture section in persistence-design.md, which explains how SQLite and LanceDB separate responsibilities.
- The write path (Architecture.md:94-106) aligns with the Write Path section in persistence-design.md:268-291.

### Architecture.md → chunking-strategy.md

| Location | Reference | Target | Status |
|----------|-----------|--------|--------|
| Line 478 | "Chunking strategy differs fundamentally across these categories" | Domain-specific overrides at chunking-strategy.md:239-266 | ✓ Valid |
| Lines 32-37 | Domain types (Messages, Notes, Events, Tasks) | Domain-specific chunking implementations at chunking-strategy.md:243-266 | ✓ Valid |

**Details:**
- Architecture.md's discussion of why four domains exist directly references the chunking rationale explained in chunking-strategy.md.
- Each domain's chunking behavior is detailed in the "Domain-Specific Overrides" section of chunking-strategy.md.

### chunking-strategy.md → persistence-design.md

| Location | Reference | Target | Status |
|----------|-----------|--------|--------|
| Line 259 | "The raw event data is stored in the document store for drill-down" | Document store definition at persistence-design.md:102 and read paths at persistence-design.md:315-372 | ✓ Valid |
| Line 282 | Cross-reference metadata concept | Lineage and metadata tracking at persistence-design.md:141-164 | ✓ Valid |

**Details:**
- The chunking strategy document assumes readers understand the document store architecture, which is fully explained in persistence-design.md.
- Context headers and metadata storage mentioned in chunking-strategy.md are reflected in the `context_header` and `domain_metadata` fields in persistence-design.md:137-143.

### Implicit Semantic Links

| From | Concept | To | Type |
|------|---------|----|----|
| Architecture.md | Chunk lineage | persistence-design.md:273-283 | Detailed schema for LineageRecord |
| Architecture.md | Diff operations | persistence-design.md:319-329 | Version diff query examples |
| chunking-strategy.md | Atomic blocks | Architecture.md:262-271 | Chunk class definition |
| chunking-strategy.md | Domain metadata | persistence-design.md:163-220 | Example domain metadata formats |

---

## Issues Addressed

### Issue 1: Recursive CTE Direction Ambiguity

**File:** persistence-design.md, lines 355-361
**Issue:** The "Version chain" CTE was titled "show me the history of this chunk" but only walks backward (ancestors), which could be unclear.
**Resolution:** Added clarifying comment explaining:
- The traversal walks backward through `parent_chunk_hash` to find ancestors (previous versions)
- Notes that to traverse forward (find descendants), one would join differently
- Confirms the direction matches the intended query: "show me the history of this chunk"

---

## Verification Results

### Cross-Reference Status
- **Total cross-references audited:** 8
- **Valid references:** 8 (100%)
- **Broken references:** 0
- **References requiring clarification:** 1 (addressed with CTE comment)

### Document Relocation Readiness
All documents are now in the `documentation/` directory with valid intra-document references. The documents use:
- **Implicit references** via section headers and topic names (no markdown links)
- **Semantic connections** through terminology and concept discussion
- **No hardcoded file paths** that would break on relocation

This approach is robust: readers can follow references by searching for key concepts rather than relying on fragile file paths.

---

## Best Practices for Future Cross-References

1. **Use semantic references** (concept names, section headers) rather than markdown links to file paths
2. **Include context headers** when discussing sections from other documents
3. **Duplicate critical definitions** across documents rather than cross-referencing—each document should be readable standalone
4. **Use consistent terminology** across all three documents for the same concepts:
   - "document store" not "SQLite document repository"
   - "vector store" not "LanceDB vector index"
   - "domain" for the four chunking categories

5. **Add clarifying comments** in complex sections (like the recursive CTE) to prevent ambiguity about traversal direction, semantics, or assumptions

---

## Related Issues

- **#37:** Schema & Database Bootstrap — May reference persistence-design.md schema definitions
- **#36:** Schema Idempotency Testing — May reference persistence-design.md migration patterns
- **#35:** Validator Error Reporting — May reference Architecture.md error handling
- **#34:** Embedding & Vector Validation — May reference persistence-design.md LanceDB schema

Monitor these issues for any schema or architecture changes that would require updating cross-references.

---

**Last Audit:** 2026-03-02
**Auditor:** Senior Software Engineer
**Status:** ✓ All cross-references verified and documented
