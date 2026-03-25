"""Post-pipeline pass that links person chunks to chunks in other domains."""

import logging
from typing import Optional

from context_library.core.exceptions import EntityLinkingError
from context_library.core.identifier_normalizer import normalize_email, normalize_phone
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    ENTITY_LINK_TYPE_PERSON_APPEARANCE,
    ChunkWithLineageContext,
    Domain,
    EntityLink,
)

logger = logging.getLogger(__name__)


class EntityLinker:
    """Post-pipeline pass that links person chunks to chunks in other domains.

    After a People adapter ingestion completes, this class performs a deterministic
    pass to scan existing chunks in other domains for person identifiers (emails, phones),
    creating entity_links rows for matches.

    Design: Uses per-person SQL scans with json_extract() on domain_metadata fields.
    This Strategy A approach is efficient for typical data volumes (hundreds to low
    thousands of contacts, tens of thousands of chunks).
    """

    def __init__(self, document_store: DocumentStore) -> None:
        """Initialize the EntityLinker with a DocumentStore.

        Args:
            document_store: The DocumentStore instance to query and update.
        """
        self._store = document_store

    def run(self) -> tuple[int, int]:
        """Execute the full entity linking pass.

        Performs these steps:
        1. Clean up entity_links for retired chunks (both source and target)
        2. Fetch active (non-retired) person chunks via pagination
        3. For each person chunk, extract emails/phones from domain_metadata
        4. For each identifier, query chunks in other domains for matches
        5. Write matched links to entity_links

        Pages are processed and discarded immediately to minimize memory usage.

        Returns:
            Tuple of (total_links_created, total_chunks_failed) where:
            - total_links_created: Number of new entity_links rows created
            - total_chunks_failed: Number of person chunks that failed to process

        Raises:
            EntityLinkingError: If cleanup fails or any uncaught error occurs.
        """
        # Step 1: Clean up entity_links for retired chunks (both source and target)
        # This ensures cleanup runs even if all person chunks are retired
        retired_links_cleaned = self._cleanup_retired_chunks_links()
        if retired_links_cleaned > 0:
            logger.info("Cleaned up %d entity_links for retired chunks", retired_links_cleaned)

        # Step 2-5: Fetch and process person chunks page by page
        # Each page is processed and discarded immediately to minimize memory usage
        page_size = 10000
        offset = 0
        total_links_created = 0
        total_chunks_failed = 0
        chunks_processed = 0
        has_chunks = False

        while True:
            person_chunks, total = self._store.list_chunks(
                domain=Domain.PEOPLE,
                limit=page_size,
                offset=offset,
            )

            if not person_chunks:
                break

            has_chunks = True
            page_links, page_failures = self._process_person_chunks_page(person_chunks)
            total_links_created += page_links
            total_chunks_failed += page_failures
            chunks_processed += len(person_chunks)

            logger.debug(
                "Entity linking: processed %d chunks from page (total processed: %d / %d, created %d links, %d failures)",
                len(person_chunks),
                chunks_processed,
                total,
                page_links,
                page_failures,
            )

            offset += len(person_chunks)

            # Break if we've fetched all chunks
            if offset >= total:
                break

        if not has_chunks:
            logger.info("No person chunks found; entity linking pass is complete")
            return 0, 0

        logger.info(
            "Entity linking pass complete: processed %d person chunks, created %d new links, %d failures",
            chunks_processed,
            total_links_created,
            total_chunks_failed,
        )
        return total_links_created, total_chunks_failed

    def _process_person_chunks_page(self, person_chunks: list[ChunkWithLineageContext]) -> tuple[int, int]:
        """Process a single page of person chunks.

        For each chunk, extracts identifiers, finds matching chunks in other domains,
        and writes entity links. Errors are logged but don't abort processing.

        Args:
            person_chunks: List of ChunkWithContext objects to process.

        Returns:
            Tuple of (new_links_created, failures_count) where:
            - new_links_created: Number of new entity_links rows created for this page
            - failures_count: Number of chunks that failed to process
        """
        page_links_created = 0
        failures = 0
        for chunk_with_context in person_chunks:
            chunk = chunk_with_context.chunk
            try:
                # Extract emails and phones from domain_metadata
                identifiers = self._extract_identifiers(chunk.domain_metadata)
                if not identifiers:
                    continue

                # Find chunks in other domains that match these identifiers
                matching_chunk_hashes = self._find_matching_chunks(identifiers)
                if not matching_chunk_hashes:
                    continue

                # Build EntityLink objects: (person_chunk_hash, matching_chunk_hash, link_type, confidence)
                links = [
                    EntityLink(chunk.chunk_hash, matching_hash, ENTITY_LINK_TYPE_PERSON_APPEARANCE, 1.0)
                    for matching_hash in matching_chunk_hashes
                ]

                # Write links (idempotent via UNIQUE constraint)
                new_links = self._store.write_entity_links(links)
                page_links_created += new_links
                if new_links > 0:
                    logger.debug(
                        "Person chunk %s: found %d new links for %d identifier(s)",
                        chunk.chunk_hash,
                        new_links,
                        len(identifiers),
                    )
            except Exception as e:
                logger.warning(
                    "Failed to link person chunk %s: %s",
                    chunk.chunk_hash,
                    e,
                    exc_info=True,
                )
                failures += 1
                continue

        return page_links_created, failures

    def _extract_identifiers(self, domain_metadata: Optional[dict]) -> list[str]:
        """Extract email and phone identifiers from PeopleMetadata.

        Identifiers are normalized:
        - Emails: lowercase, stripped of whitespace
        - Phones: digits and leading '+' only, extra formatting removed

        Args:
            domain_metadata: Serialized PeopleMetadata dict from chunk.domain_metadata.

        Returns:
            List of normalized email and phone strings, deduplicated and sorted.
        """
        if not domain_metadata:
            return []

        identifiers: set[str] = set()

        # Extract and normalize emails from PeopleMetadata
        if "emails" in domain_metadata:
            emails = domain_metadata.get("emails")
            if isinstance(emails, (list, tuple)):
                for e in emails:
                    if e:
                        normalized = normalize_email(str(e))
                        if normalized:
                            identifiers.add(normalized)
            elif isinstance(emails, str):
                normalized = normalize_email(emails)
                if normalized:
                    identifiers.add(normalized)

        # Extract and normalize phones from PeopleMetadata
        if "phones" in domain_metadata:
            phones = domain_metadata.get("phones")
            if isinstance(phones, (list, tuple)):
                for p in phones:
                    if p:
                        normalized = normalize_phone(str(p))
                        if normalized:
                            identifiers.add(normalized)
            elif isinstance(phones, str):
                normalized = normalize_phone(phones)
                if normalized:
                    identifiers.add(normalized)

        return sorted(list(identifiers))

    def _find_matching_chunks(self, identifiers: list[str]) -> list[str]:
        """Query chunks where domain_metadata contains any of the given identifiers.

        Delegates to DocumentStore.query_chunks_by_identifiers() for safe, concurrent access.
        Returns chunks from non-people domains matching the identifiers.

        Args:
            identifiers: List of email/phone strings to search for.

        Returns:
            List of chunk_hashes from non-people domains where a match was found.
        """
        if not identifiers:
            return []

        # Define fields to search: scalar fields (sender, host, author) and
        # array fields (recipients, invitees, collaborators) in domain_metadata
        scalar_fields = ["sender", "host", "author"]
        array_fields = ["recipients", "invitees", "collaborators"]

        return self._store.query_chunks_by_identifiers(
            identifiers,
            scalar_fields=scalar_fields,
            array_fields=array_fields,
            exclude_domain=Domain.PEOPLE,
        )

    def _cleanup_retired_chunks_links(self) -> int:
        """Clean up entity_links for all retired chunks (both source and target).

        Performs two atomic cleanup operations using DELETE ... WHERE NOT EXISTS
        to eliminate TOCTOU race conditions:
        1. Atomically deletes entity_links where source_chunk_hash is a retired person chunk
        2. Atomically deletes entity_links where target_chunk_hash is any retired chunk

        This ensures that when chunks are retired (deleted), their entity_links rows
        don't persist and cause orphaned references. The atomic operations ensure that
        concurrent ingestion cannot un-retire a chunk between read and delete.

        Returns:
            Number of rows deleted.

        Raises:
            EntityLinkingError: If cleanup fails for any reason.
        """
        try:
            total_deleted = 0

            # Step 1: Atomically delete entity_links where source_chunk_hash is a retired
            # person chunk. Uses DELETE ... WHERE NOT EXISTS to avoid TOCTOU race.
            deleted = self._store.delete_retired_person_links_atomic()
            total_deleted += deleted

            # Step 2: Atomically delete entity_links where target_chunk_hash is a retired
            # chunk in any domain. Uses DELETE ... WHERE NOT EXISTS to avoid TOCTOU race.
            deleted = self._store.delete_retired_target_links_atomic()
            total_deleted += deleted

            return total_deleted
        except Exception as e:
            raise EntityLinkingError(f"Failed to clean up retired chunk links: {e}") from e
