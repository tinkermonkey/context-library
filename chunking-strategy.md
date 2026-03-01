# Chunking Strategy Guide

How to decompose structured markdown documents into chunks that preserve meaning, context, and retrievability — especially when documents contain mixed content types like code blocks, tables, images, and nested structures.

---

## The Core Problem

Naive chunking (split every N tokens with overlap) destroys the very structure that makes documents useful. A code block split across two chunks is two useless fragments. A table header separated from its rows is noise. An image caption in a different chunk than the image it describes is a retrieval trap — you'll find the caption but lose the visual context.

Structured documents have **semantic boundaries** that must be respected, and **context dependencies** that must be preserved even when content is split.

---

## Principles

### 1. Boundary Hierarchy

Not all boundaries are equal. A heading is a stronger boundary than a paragraph break, which is stronger than a sentence break. Chunking should prefer splitting at the strongest available boundary that keeps chunks within the target size range.

The hierarchy, from strongest to weakest:

```
H1 heading
  H2 heading
    H3+ heading
      Thematic break (---)
        Block-level element boundary (end of code block, table, blockquote)
          Paragraph break (blank line)
            Sentence boundary
              (Never: mid-sentence, mid-code-block, mid-table)
```

The algorithm walks the document's structure, accumulating content until the target size is approached, then splits at the strongest boundary within a lookback window. If no good boundary exists within the window, the chunk is allowed to exceed the soft target rather than break a semantic unit.

### 2. Atomic Blocks

Some content types are **atomic** — splitting them always destroys meaning. These must be kept whole or, if they exceed the chunk size limit, handled with special strategies.

Atomic blocks:

- **Code blocks:** A function definition split in half is useless for retrieval and hallucination-prone for generation. Keep whole.
- **Tables:** Header row + data rows are a unit. A table without its headers is uninterpretable.
- **Images with captions:** The image reference and its immediately adjacent description text (caption, alt text, surrounding explanatory paragraph) form a unit.
- **Math blocks:** A LaTeX equation split mid-expression is garbage.
- **Blockquotes:** Usually a single attributed thought. Keep whole unless very long.
- **List items with sub-lists:** A parent item and its children are a logical group.

If an atomic block exceeds the maximum chunk size on its own, it becomes a **standalone chunk** that's allowed to exceed the limit, tagged with a `chunk_type` indicating it's an oversized atomic block. This is better than breaking it.

### 3. Context Headers

When a chunk doesn't start at the beginning of a document, it loses the structural context that tells you *where* in the document it lives. A paragraph about "the second parameter" means nothing without knowing which function's documentation you're in.

Every chunk should carry a **context header** — a breadcrumb trail of the heading hierarchy above it:

```
# API Reference > ## Authentication > ### OAuth Flow

The second parameter specifies the redirect URI...
```

This header is prepended to the chunk content before embedding. It's lightweight (rarely more than a few lines) but dramatically improves retrieval relevance because the embedding now captures the structural location, not just the local content.

The context header is metadata, not part of the chunk's content hash. The same paragraph under a different heading structure would produce a different embedding but could still be recognized as the same content for versioning purposes.

### 4. Soft and Hard Limits

Chunks have two size thresholds:

- **Soft target** (e.g., 512 tokens): The ideal size. The algorithm tries to split near this boundary.
- **Hard maximum** (e.g., 1024 tokens): The absolute ceiling. Only atomic blocks are allowed to exceed this, and they're flagged when they do.

Chunks below a **minimum floor** (e.g., 64 tokens) are merged into the previous chunk rather than standing alone — a two-sentence chunk is usually too thin to embed meaningfully.

---

## Algorithm: Structure-Aware Recursive Chunking

### Phase 1: Parse to Block Tree

Before chunking, parse the markdown into a tree of typed blocks. This isn't a full AST — it's a lightweight structural parse that identifies block types and nesting.

```
Document
├── Heading(1, "Installation")
│   ├── Paragraph("Clone the repository...")
│   ├── CodeBlock(lang="bash", "git clone ...")
│   └── Paragraph("Then install dependencies...")
├── Heading(1, "Configuration")
│   ├── Heading(2, "Environment Variables")
│   │   ├── Paragraph("The following variables...")
│   │   ├── Table(headers=["Name","Required","Default"], rows=[...])
│   │   └── Paragraph("All variables can be...")
│   └── Heading(2, "Config File")
│       ├── Paragraph("Alternatively, create...")
│       ├── CodeBlock(lang="yaml", "database:\n  host: ...")
│       └── ImageRef(alt="Config file location", path="config-screenshot.png")
└── Heading(1, "Usage")
    └── ...
```

Each node knows its type, its content size (in tokens), and its children.

### Phase 2: Measure and Annotate

Walk the tree bottom-up, annotating each node with:

- **self_size**: Token count of just this node's direct content (not children).
- **subtree_size**: Total token count including all descendants.
- **is_atomic**: Whether this node must be kept whole.
- **can_split_children**: Whether this node's children can be distributed across chunks.

A heading node with subtree_size under the soft target can be emitted as a single chunk. A heading node with subtree_size over the soft target needs its children distributed across multiple chunks, each carrying the heading as context.

### Phase 3: Recursive Descent Chunking

```
function chunk(node, context_headers, accumulator):
    if node is atomic AND node.subtree_size ≤ hard_max:
        # Keep it whole. Flush accumulator if adding this would exceed soft target.
        if accumulator.size + node.subtree_size > soft_target:
            emit(accumulator, context_headers)
            accumulator = new
        accumulator.append(node)

    else if node.subtree_size ≤ soft_target:
        # Entire subtree fits in one chunk. Treat as a unit.
        if accumulator.size + node.subtree_size > soft_target:
            emit(accumulator, context_headers)
            accumulator = new
        accumulator.append(node.full_content)

    else if node is heading:
        # Subtree too large — recurse into children with updated context.
        emit(accumulator, context_headers)  # flush before new section
        new_context = context_headers + [node.heading_text]
        child_accumulator = new
        for child in node.children:
            child_accumulator = chunk(child, new_context, child_accumulator)
        emit(child_accumulator, new_context)  # flush remainder

    else if node is atomic AND node.subtree_size > hard_max:
        # Oversized atomic block — emit as standalone oversized chunk.
        emit(accumulator, context_headers)
        emit(node.full_content, context_headers, oversized=true)
        accumulator = new

    else:
        # Non-atomic, non-heading, too large (e.g., very long paragraph).
        # Split at sentence boundaries.
        emit(accumulator, context_headers)
        for sentence_group in split_sentences(node, soft_target):
            emit(sentence_group, context_headers)
        accumulator = new

    return accumulator
```

### Phase 4: Post-Processing

After initial chunking:

1. **Merge runts**: Any chunk below the minimum floor gets merged into the previous chunk (even if that pushes it over the soft target slightly).
2. **Attach orphaned context**: If a chunk consists only of a heading with no body content, merge it forward into the next chunk.
3. **Compute hashes**: Hash each chunk's content (without the context header) for versioning.
4. **Generate context headers**: Prepend the heading breadcrumb trail to each chunk's content for embedding.

---

## Handling Specific Content Types

### Code Blocks

**Goal:** Never split a code block.

- Code blocks under the hard maximum are atomic — always kept whole.
- Code blocks over the hard maximum become standalone oversized chunks. In practice this is rare (a 1024-token code block is ~80 lines), and when it happens, oversized is better than split.
- The immediately preceding paragraph (which usually describes what the code does) should be grouped with the code block when possible. A code block without its introductory sentence is significantly less useful for retrieval.
- Language metadata (` ```python `) is preserved in the chunk — it affects embedding quality and retrieval relevance.

### Tables

**Goal:** Never separate headers from data.

- Tables under the hard maximum are atomic.
- Tables over the hard maximum can be split **by row groups** only if each resulting chunk carries the header row. This is the one exception to "atomic means never split" — a 200-row table is more useful as 4 chunks of 50 rows (each with headers) than as one enormous chunk.
- When splitting tables, each chunk gets: the context header, the table's header row, and its subset of data rows. The chunk is tagged with `table_part: 1/4` metadata for reconstruction.

### Images

**Goal:** Keep the image reference bundled with its descriptive context.

Images in markdown are references (`![alt](path)`), not inline binary data. The chunking concern is keeping the reference co-located with the text that gives it meaning.

An image reference forms a unit with:

1. Its alt text (always — it's part of the reference syntax).
2. The immediately preceding or following paragraph, if it describes the image (caption detection heuristic: short paragraph adjacent to image, often starting with "Figure", "Screenshot", "The above shows", etc.).
3. Any figure label or number.

This unit is treated as atomic. If the image's descriptive context is ambiguous (long paragraph that happens to be near an image), err on the side of including more context — a chunk with extra text is better than an image reference with no explanation.

For **domain-specific image handling** (e.g., photos of handwritten notes in the Notes domain), the image should be processed by a vision LLM *before* chunking. The resulting text description replaces the image reference in the markdown, and chunking proceeds on the textual description. The original image path is preserved in the lineage metadata.

### Blockquotes

**Goal:** Keep the quoted content as a unit.

- Blockquotes are atomic blocks — they represent a single attributed thought or citation.
- Nested blockquotes (replies in forum-style content) maintain their nesting. The outermost blockquote is the atomic boundary.
- For the Messages domain, blockquotes often represent quoted replies and should carry the reply-chain metadata from the domain layer.

### Lists

**Goal:** Preserve parent-child relationships. Allow splitting between top-level items.

Lists have two levels of structure:

- **Top-level items**: These are valid split points. A chunk can contain items 1-3 and another can contain items 4-6.
- **Item + sub-items**: These are atomic. If item 2 has sub-items a, b, c, they stay together.

When splitting a list across chunks, each chunk should carry any introductory text that precedes the list ("The following configuration options are available:") as context.

Numbered lists that are split should carry their original numbering — don't restart at 1 in the second chunk. This preserves the ability to reference "step 5" in retrieval.

### Nested / Mixed Structures

Real documents nest these types: a list item containing a code block inside a blockquote under a heading. The rules compose:

1. Parse the nesting structure into the block tree.
2. Atomic-ness propagates upward: if a list item contains an atomic code block, the list item is effectively atomic (its minimum size includes the code block).
3. Apply the recursive algorithm — it naturally handles nesting because it walks the tree.

The main risk is **atomic block accumulation**: a section with three code blocks and three paragraphs where each code-block-plus-paragraph exceeds the soft target individually. The algorithm handles this correctly by emitting each group as its own chunk, all sharing the same context header.

---

## Domain-Specific Overrides

The algorithm above is the default. Each domain applies modifications:

### Messages

- Chunk boundary defaults to **message boundary** (one message per chunk, or a small thread window).
- Context header is replaced by **thread context**: participants, subject, timestamp range.
- No need for heading-based hierarchy — the structure is flat (messages in sequence).

### Notes

- Standard algorithm applies with no major modifications.
- Temporal metadata (created/modified timestamps) is attached to every chunk.
- For photo-to-text notes, the vision LLM output is chunked as regular markdown, with the source image path in lineage.

### Events

- Not chunked from markdown at all. Events are structured records batched into time windows.
- The "chunk" is a generated natural-language summary of the window, produced by the domain layer.
- The summary is what gets embedded. The raw event data is stored in the document store for drill-down.

### Tasks

- Each task is typically one chunk (title + description + metadata).
- Project/workstream hierarchy serves as the context header equivalent.
- State transitions generate new chunk versions even if the text content hasn't changed — the domain layer synthesizes a textual description of the state change for embedding.

---

## Chunk Overlap and Cross-References

### Overlap

Traditional chunking uses token overlap (last N tokens of chunk K become the first N tokens of chunk K+1) to avoid losing context at boundaries. Structure-aware chunking largely eliminates this need because it splits at semantic boundaries, but there are cases where lightweight overlap helps:

- **Long prose sections** (no headings, no code, just paragraphs) that must be split at sentence boundaries benefit from 1-2 sentence overlap.
- **Context headers** serve as a form of structural overlap — they repeat the heading context without repeating content.

Overlap is **not used** for code blocks, tables, or other atomic types. It's a prose-only concern.

### Cross-References

When a chunk contains a reference to content in another chunk (e.g., "as shown in the table above", "see the function defined in Section 2"), the reference is noted in metadata as a `cross_ref` pointing to the referenced chunk's hash. This enables retrieval to pull in referenced chunks as additional context when a cross-referencing chunk is retrieved.

Cross-reference detection is heuristic and best-effort: look for phrases like "above", "below", "see Section X", "as defined in", "the following table". False positives are harmless (extra context in retrieval). False negatives mean slightly less context, which is the status quo for most RAG systems anyway.

---

## Size Tuning

The soft target, hard maximum, and minimum floor are tunable per domain and even per adapter, but reasonable defaults:

| Parameter | Default | Notes |
|-----------|---------|-------|
| Soft target | 512 tokens | Good balance for most embedding models. Larger targets (768-1024) work better for long-form notes. Smaller (256-384) work better for messages. |
| Hard maximum | 1024 tokens | 2x the soft target. Only atomic blocks exceed this. |
| Minimum floor | 64 tokens | Below this, a chunk is too thin to embed meaningfully. Merge into neighbor. |
| Context header budget | 128 tokens | Maximum size of the prepended heading breadcrumb. Deep nesting gets truncated to innermost headings. |
| Prose overlap | 2 sentences | Only applied to prose splits, not structural boundaries. |

These should be validated empirically by running retrieval evals on representative documents and adjusting. The algorithm's structure means changing sizes doesn't change the logic — just where the splits fall.
