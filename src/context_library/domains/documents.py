"""Documents domain chunker for document content."""

from pydantic import ValidationError

from context_library.domains.base import BaseDomain
from context_library.storage.models import (
    Chunk,
    ChunkType,
    DocumentMetadata,
    NormalizedContent,
    compute_chunk_hash,
)


class DocumentsDomain(BaseDomain):
    """Domain-specific chunker for document content.

    Extracts DocumentMetadata from extra_metadata, builds title-based context
    headers, and uses whole-document chunking with _split_if_needed() for
    oversized content.
    """

    def __init__(self, hard_limit: int = 1024) -> None:
        """Initialize the DocumentsDomain chunker.

        Args:
            hard_limit: Maximum token limit before forced splitting (default 1024)

        Raises:
            ValueError: If hard_limit is not a positive integer
        """
        super().__init__(hard_limit)

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Chunk document content into semantically coherent pieces.

        Algorithm:
        1. Extract and validate DocumentMetadata from extra_metadata
        2. Build context_header in "{title} — {document_type}" format
        3. Guard against empty markdown body
        4. Split content if needed using hard_limit
        5. Create chunks with sequential indices and domain metadata
        6. Apply cross-reference detection

        Args:
            content: Normalized document content with metadata

        Returns:
            List of chunks, or empty list if markdown body is empty

        Raises:
            ValueError: If extra_metadata is missing or validation fails
        """
        # 1. Guard: require extra_metadata
        if not content.structural_hints.extra_metadata:
            raise ValueError(
                f"DocumentsDomain requires extra_metadata in structural_hints "
                f"for source {content.source_id}"
            )

        meta_dict = content.structural_hints.extra_metadata

        # 2. Validate via DocumentMetadata
        try:
            meta = DocumentMetadata(**meta_dict)  # type: ignore[arg-type]
        except ValidationError as e:
            raise ValueError(
                f"Invalid DocumentMetadata for source {content.source_id}: "
                f"{e.error_count()} validation error(s) — "
                f"{[err['msg'] for err in e.errors()]}"
            ) from e

        # 3. Build context_header in "{title} — {document_type}" format
        context_header = f"{meta.title} — {meta.document_type}"

        # 4. Get body and guard against empty markdown
        text = content.markdown.strip()
        if not text:
            return []

        # 5. Split if needed
        segments = self._split_if_needed(text)

        # 6. Build chunks with sequential indices
        chunks = []
        for idx, segment in enumerate(segments):
            chunk_hash = compute_chunk_hash(segment)
            # Merge: validated fields take precedence over raw dict
            # This ensures Pydantic normalization is preserved
            domain_metadata = {**meta_dict, **meta.model_dump(exclude_none=True)}
            chunk = Chunk(
                chunk_hash=chunk_hash,
                content=segment,
                context_header=context_header,
                chunk_index=idx,
                chunk_type=ChunkType.STANDARD,
                domain_metadata=domain_metadata,
            )
            chunks.append(chunk)

        # 7. Apply cross-reference detection
        return self._apply_cross_references(chunks)
