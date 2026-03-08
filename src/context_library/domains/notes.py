"""NotesDomain: chunking and metadata for freeform notes."""

import logging
import re
from typing import Any, TypedDict

import mistune

from context_library.core.exceptions import ChunkingError
from context_library.domains.base import BaseDomain
from context_library.storage.models import (
    Chunk,
    ChunkType,
    NormalizedContent,
    compute_chunk_hash,
)

logger = logging.getLogger(__name__)


class CandidateChunk(TypedDict):
    """TypedDict for candidate chunk dictionaries.

    All fields are required (total=True by default) as every candidate chunk
    construction site includes all five fields. This strengthens the type contract
    and prevents accidental omission of required metadata.

    chunk_type is typed as ChunkType to enforce valid chunk type values.
    """

    content: str
    context_header: str | None
    chunk_type: ChunkType
    domain_metadata: dict[str, Any] | None
    is_atomic: bool


class NotesDomain(BaseDomain):
    """Domain-specific chunker for freeform markdown notes.

    Splits markdown content into semantically coherent chunks using heading-based hierarchy,
    respecting code block and table atomicity, with context headers as heading breadcrumbs.
    """

    def __init__(
        self, soft_limit: int = 512, hard_limit: int = 1024
    ):
        """Initialize the NotesDomain chunker.

        Args:
            soft_limit: Target token limit for joining adjacent sections (default 512)
            hard_limit: Maximum token limit before forced splitting (default 1024)

        Raises:
            ValueError: If hard_limit is not a positive integer
        """
        super().__init__(hard_limit)
        if soft_limit <= 0:
            raise ValueError(
                f"soft_limit must be a positive integer, got {soft_limit}"
            )
        self.soft_limit = soft_limit
        # Create markdown parser with renderer=None to get AST output
        # Enable table plugin to recognize markdown tables
        self.md = mistune.create_markdown(renderer=None, plugins=["table"])

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Split markdown content into semantically coherent chunks.

        Algorithm:
        1. Parse markdown to AST using mistune
        2. Walk AST to identify block types (headings, code blocks, tables, paragraphs)
        3. Split on headings - each heading and subsequent content until next same-or-higher heading
        4. Keep code blocks and tables atomic
        5. Generate context headers as heading breadcrumb paths
        6. Respect soft/hard token limits with paragraph-boundary splitting
        7. Compute chunk_hash from normalized content (excluding context header)
        8. Store context header separately from content in Chunk model
        9. Assign sequential chunk_index values
        10. Extract domain metadata from extra_metadata and propagate to Chunk.domain_metadata

        Args:
            content: The normalized markdown content to chunk

        Returns:
            A list of Chunk instances with sequential chunk_index values
        """
        # Parse markdown to AST
        # mistune returns str | list[dict[str, Any]] but with renderer=None we always get list
        ast_result = self.md(content.markdown)
        if not isinstance(ast_result, list):
            raise ChunkingError(
                f"Markdown parser returned unexpected type {type(ast_result).__name__} instead of list. "
                f"Cannot chunk content from source {content.source_id}.",
                source_id=content.source_id,
            )
        ast = ast_result

        # Build candidate chunks from AST
        candidates = self._build_candidates(ast)

        # Apply token limits: join short sections, split oversized ones
        final_chunks = self._apply_token_limits(candidates)

        # Extract domain metadata from extra_metadata (e.g., from adapters like ObsidianAdapter)
        # This metadata (tags, aliases, wikilinks, backlinks, etc.) is stored in structural_hints
        # and should be propagated to every chunk's domain_metadata
        extra_metadata = content.structural_hints.extra_metadata or {}

        # Compute hashes and assign indices
        chunks = []
        for index, candidate in enumerate(final_chunks):
            # Content hash is computed from content alone (excluding context header)
            chunk_hash = compute_chunk_hash(candidate["content"])

            # Merge domain metadata from candidate with extra metadata from adapter
            # Candidate metadata (e.g., heading_level) takes precedence over extra metadata
            domain_metadata = dict(extra_metadata)
            candidate_metadata = candidate.get("domain_metadata")
            if candidate_metadata:
                domain_metadata.update(candidate_metadata)

            chunk = Chunk(
                chunk_hash=chunk_hash,
                content=candidate["content"],
                context_header=candidate["context_header"],
                chunk_index=index,
                chunk_type=candidate["chunk_type"],
                domain_metadata=domain_metadata if domain_metadata else None,
            )
            chunks.append(chunk)

        return chunks

    def _build_candidates(self, ast: list[dict[str, Any]]) -> list[CandidateChunk]:
        """Build candidate chunks from AST by walking block structure.

        Splits on headings, preserving hierarchy with a heading stack.
        Keeps code blocks and tables atomic.

        Args:
            ast: The mistune AST (list of block dicts)

        Returns:
            A list of candidate chunk dicts with content, context_header, chunk_type, etc.
        """
        candidates: list[CandidateChunk] = []
        heading_stack: list[tuple[int, str]] = []  # Stack of (level, text) tuples
        current_candidate: CandidateChunk | None = None

        for block in ast:
            block_type = block.get("type")

            # Skip blank lines - they're just formatting
            if block_type == "blank_line":
                continue

            if block_type == "heading":
                # Flush current candidate if exists
                if current_candidate and current_candidate["content"].strip():
                    candidates.append(current_candidate)

                # Update heading stack
                level = block["attrs"]["level"]
                # Pop all headings at level >= current level
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                # Extract heading text from children
                heading_text = self._extract_text_from_children(block.get("children", []))
                heading_stack.append((level, heading_text))

                # Start new candidate
                context_header = self._build_context_header(heading_stack)
                current_candidate = {
                    "content": "",
                    "context_header": context_header,
                    "chunk_type": ChunkType.STANDARD,
                    "domain_metadata": {"heading_level": level},
                    "is_atomic": False,
                }

            elif block_type == "block_code":
                # Code blocks are atomic - flush current if needed
                if current_candidate and current_candidate["content"].strip():
                    candidates.append(current_candidate)

                # Create atomic code block chunk
                code_content = block.get("raw", "")
                context_header = (
                    self._build_context_header(heading_stack) if heading_stack else None
                )
                candidates.append(
                    {
                        "content": code_content,
                        "context_header": context_header,
                        "chunk_type": ChunkType.CODE,
                        "domain_metadata": None,
                        "is_atomic": True,
                    }
                )

                # Start fresh candidate
                current_candidate = {
                    "content": "",
                    "context_header": context_header,
                    "chunk_type": ChunkType.STANDARD,
                    "domain_metadata": (
                        {"heading_level": heading_stack[-1][0]}
                        if heading_stack
                        else None
                    ),
                    "is_atomic": False,
                }

            elif block_type == "table":
                # Tables are atomic - flush current if needed
                if current_candidate and current_candidate["content"].strip():
                    candidates.append(current_candidate)

                # Create atomic table chunk
                table_content = self._extract_table_markdown(block)
                context_header = (
                    self._build_context_header(heading_stack) if heading_stack else None
                )
                candidates.append(
                    {
                        "content": table_content,
                        "context_header": context_header,
                        "chunk_type": ChunkType.TABLE,
                        "domain_metadata": None,
                        "is_atomic": True,
                    }
                )

                # Start fresh candidate
                current_candidate = {
                    "content": "",
                    "context_header": context_header,
                    "chunk_type": ChunkType.STANDARD,
                    "domain_metadata": (
                        {"heading_level": heading_stack[-1][0]}
                        if heading_stack
                        else None
                    ),
                    "is_atomic": False,
                }

            else:
                # Accumulate other block types (paragraph, list, block_quote, etc.)
                if current_candidate is None:
                    context_header = (
                        self._build_context_header(heading_stack) if heading_stack else None
                    )
                    current_candidate = {
                        "content": "",
                        "context_header": context_header,
                        "chunk_type": ChunkType.STANDARD,
                        "domain_metadata": (
                            {"heading_level": heading_stack[-1][0]}
                            if heading_stack
                            else None
                        ),
                        "is_atomic": False,
                    }

                # Render block to markdown and append
                block_markdown = self._render_block_to_markdown(block)
                if current_candidate["content"]:
                    current_candidate["content"] += "\n\n" + block_markdown
                else:
                    current_candidate["content"] = block_markdown

        # Flush final candidate
        if current_candidate and current_candidate["content"].strip():
            candidates.append(current_candidate)

        return candidates

    def _extract_text_from_children(self, children: list[dict[str, Any]]) -> str:
        """Recursively extract text from inline children.

        Handles both text nodes with 'raw' field and nodes with 'children'.
        Special handling for inline nodes that have 'raw' but no 'children'
        (e.g., codespan, html_inline).
        """
        text = ""
        for child in children:
            child_type = child.get("type")
            # Nodes with 'raw' field (text, codespan, html_inline, etc.)
            if child_type in ("text", "codespan", "html_inline"):
                text += child.get("raw", "")
            # Nodes with 'children' (emphasis, strong, link, image, etc.)
            elif "children" in child:
                text += self._extract_text_from_children(child.get("children", []))
        return text

    def _build_context_header(self, heading_stack: list[tuple[int, str]]) -> str | None:
        """Build context header as breadcrumb from heading stack.

        Format: "# H1 text > ## H2 text > ### H3 text"

        Args:
            heading_stack: List of (level, text) tuples

        Returns:
            Context header string or None if stack is empty
        """
        if not heading_stack:
            return None

        parts = []
        for level, text in heading_stack:
            hashes = "#" * level
            parts.append(f"{hashes} {text}")

        return " > ".join(parts)

    def _render_block_to_markdown(self, block: dict[str, Any]) -> str:
        """Render a block to markdown text."""
        block_type = block.get("type")

        if block_type == "paragraph":
            return self._extract_text_from_children(block.get("children", []))

        elif block_type == "list":
            return self._render_list(block)

        elif block_type == "block_quote":
            return self._render_block_quote(block)

        elif block_type == "thematic_break":
            return "---"

        else:
            # Attempt best-effort content extraction for unrecognized block types
            content = ""

            # Try to extract from 'raw' field (e.g., block_html, math_block)
            if "raw" in block:
                content = block.get("raw", "")

            # Try to extract from 'children' field (e.g., def_list, footnote)
            elif "children" in block:
                content = self._extract_text_from_children(block.get("children", []))

            # Log warning if content was unavailable
            if not content:
                logger.warning(
                    "Unrecognized markdown block type '%s' - no content extracted. "
                    "Block keys: %s",
                    block_type,
                    list(block.keys()),
                )

            return content

    def _render_list(self, block: dict[str, Any]) -> str:
        """Render a list block to markdown."""
        items = block.get("children", [])
        lines = []
        is_ordered = block.get("attrs", {}).get("ordered", False)

        item_number = 0
        for item in items:
            item_type = item.get("type")
            if item_type == "list_item":
                item_number += 1
                # Get text from item children
                text = self._extract_text_from_children(item.get("children", []))
                # Use numbered prefix for ordered lists, dash for unordered
                if is_ordered:
                    lines.append(f"{item_number}. {text}")
                else:
                    lines.append(f"- {text}")

        return "\n".join(lines)

    def _render_block_quote(self, block: dict[str, Any]) -> str:
        """Render a block quote to markdown."""
        children = block.get("children", [])
        lines = []

        for child in children:
            child_text = self._render_block_to_markdown(child)
            for line in child_text.split("\n"):
                lines.append(f"> {line}")

        return "\n".join(lines)

    def _extract_table_markdown(self, block: dict[str, Any]) -> str:
        """Extract table content as markdown."""
        # For simplicity, reconstruct a basic table markdown representation
        # from the AST structure.
        # Note: In mistune 3.x, table_head has table_cell nodes as direct children,
        # while table_body wraps cells in table_row nodes.
        children = block.get("children", [])
        lines = []

        for section in children:
            section_type = section.get("type")
            if section_type == "table_head":
                # table_head children are table_cell nodes directly (no table_row wrapper)
                cells = []
                for cell in section.get("children", []):
                    if cell.get("type") == "table_cell":
                        cell_text = self._extract_text_from_children(
                            cell.get("children", [])
                        )
                        cells.append(cell_text)
                if cells:
                    lines.append("| " + " | ".join(cells) + " |")
                    # Add separator line after header
                    separator = "| " + " | ".join(["---"] * len(cells)) + " |"
                    lines.append(separator)

            elif section_type == "table_body":
                # table_body children are table_row nodes
                for row in section.get("children", []):
                    cells = []
                    for cell in row.get("children", []):
                        cell_text = self._extract_text_from_children(
                            cell.get("children", [])
                        )
                        cells.append(cell_text)
                    if cells:
                        lines.append("| " + " | ".join(cells) + " |")

        return "\n".join(lines)

    def _apply_token_limits(self, candidates: list[CandidateChunk]) -> list[CandidateChunk]:
        """Apply soft and hard token limits to candidate chunks.

        Algorithm:
        1. Join short adjacent sections below soft_limit if combined size <= hard_limit
           (but NOT sections with different context headers - those are separate heading sections)
        2. Split oversized sections exceeding hard_limit at paragraph boundaries

        Args:
            candidates: List of candidate chunk dicts

        Returns:
            Adjusted list of chunk dicts
        """
        if not candidates:
            return []

        result: list[CandidateChunk] = []
        i = 0

        while i < len(candidates):
            current = candidates[i].copy()
            current_tokens = self._token_count(current["content"])

            # Try to join with next sections if current is below soft_limit
            # BUT: don't join sections with different context headers (different heading sections)
            if current_tokens < self.soft_limit and i + 1 < len(candidates):
                # Accumulate adjacent sections
                while (
                    i + 1 < len(candidates)
                    and self._token_count(current["content"]) < self.hard_limit
                ):
                    next_candidate = candidates[i + 1]

                    # Don't merge atomic blocks
                    if current.get("is_atomic") or next_candidate.get("is_atomic"):
                        break

                    # Don't merge sections with different context headers
                    # (they're under different headings and should stay separate)
                    if current.get("context_header") != next_candidate.get("context_header"):
                        break

                    combined_tokens = self._token_count(
                        current["content"] + "\n\n" + next_candidate["content"]
                    )
                    if combined_tokens <= self.hard_limit:
                        current["content"] += "\n\n" + next_candidate["content"]
                        i += 1
                    else:
                        break

            # Check if current needs splitting due to hard_limit
            if self._token_count(current["content"]) > self.hard_limit and not current.get(
                "is_atomic"
            ):
                split_chunks = self._split_oversized_chunk(current)
                result.extend(split_chunks)
            else:
                result.append(current)

            i += 1

        return result

    def _split_oversized_chunk(self, chunk: CandidateChunk) -> list[CandidateChunk]:
        """Split an oversized chunk at paragraph boundaries.

        When paragraphs exceed hard_limit, split at sentence boundaries.
        When sentences exceed hard_limit, split at word boundaries.

        Args:
            chunk: The chunk dict to split

        Returns:
            A list of smaller chunk dicts
        """
        content = chunk["content"]
        context_header = chunk["context_header"]
        chunk_type = chunk["chunk_type"]
        domain_metadata = chunk.get("domain_metadata")

        # Split into paragraphs (double newline separated)
        paragraphs = re.split(r"\n\n+", content)

        result: list[CandidateChunk] = []
        current_chunk = ""

        for para in paragraphs:
            if not para.strip():
                continue

            para_tokens = self._token_count(para)

            # If a single paragraph exceeds hard_limit, try sentence boundaries first
            if para_tokens > self.hard_limit:
                # Split at sentence boundaries using lookbehind to keep punctuation attached
                # This produces clean sentences like "Hello world." instead of "Hello world . "
                sentences = re.split(r'(?<=[.!?])\s+', para)
                # Filter out empty strings from the split
                sentences = [s for s in sentences if s.strip()]

                for sent in sentences:
                    if not sent.strip():
                        continue

                    sent_tokens = self._token_count(sent)

                    # If sentence itself exceeds hard_limit, split at word boundaries
                    if sent_tokens > self.hard_limit:
                        words = sent.split()
                        for word in words:
                            test_chunk = (current_chunk + " " + word).strip()

                            if self._token_count(test_chunk) <= self.hard_limit:
                                current_chunk = test_chunk
                            else:
                                # Flush current and start new
                                if current_chunk:
                                    result.append(
                                        {
                                            "content": current_chunk,
                                            "context_header": context_header,
                                            "chunk_type": chunk_type,
                                            "domain_metadata": domain_metadata,
                                            "is_atomic": False,
                                        }
                                    )
                                current_chunk = word
                    else:
                        # Sentence fits - try to add to current chunk
                        test_chunk = (current_chunk + " " + sent).strip()
                        if self._token_count(test_chunk) <= self.hard_limit:
                            current_chunk = test_chunk
                        else:
                            # Flush current and start new
                            if current_chunk:
                                result.append(
                                    {
                                        "content": current_chunk,
                                        "context_header": context_header,
                                        "chunk_type": chunk_type,
                                        "domain_metadata": domain_metadata,
                                        "is_atomic": False,
                                    }
                                )
                            current_chunk = sent.strip()
            else:
                # Paragraph fits - try to add to current chunk
                test_chunk = (current_chunk + "\n\n" + para).strip()
                if self._token_count(test_chunk) <= self.hard_limit:
                    current_chunk = test_chunk
                else:
                    # Flush current and start new
                    if current_chunk:
                        result.append(
                            {
                                "content": current_chunk,
                                "context_header": context_header,
                                "chunk_type": chunk_type,
                                "domain_metadata": domain_metadata,
                                "is_atomic": False,
                            }
                        )
                    current_chunk = para

        # Flush final chunk
        if current_chunk:
            result.append(
                {
                    "content": current_chunk.strip(),
                    "context_header": context_header,
                    "chunk_type": chunk_type,
                    "domain_metadata": domain_metadata,
                    "is_atomic": False,
                }
            )

        return result
