"""Post-pipeline pass that links person chunks to chunks in other domains."""

import logging
from typing import Optional

from context_library.storage.document_store import DocumentStore
from context_library.storage.models import Domain

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

    LINKED_FIELDS = ["sender", "recipients", "host", "invitees", "collaborators", "author"]

    def __init__(self, document_store: DocumentStore) -> None:
        """Initialize the EntityLinker with a DocumentStore.

        Args:
            document_store: The DocumentStore instance to query and update.
        """
        self._store = document_store

    def run(self) -> int:
        """Execute the full entity linking pass.

        Performs these steps:
        1. Clean up entity_links for retired person chunks
        2. Fetch all active (non-retired) person chunks
        3. For each person chunk, extract emails/phones from domain_metadata
        4. For each identifier, query chunks in other domains for matches
        5. Write matched links to entity_links

        Returns:
            Number of new entity_links rows created.
        """
        # Step 1: Clean up entity_links for retired person chunks BEFORE fetching active chunks
        # This ensures cleanup runs even if all person chunks are retired
        retired_links_cleaned = self._cleanup_retired_person_links()
        if retired_links_cleaned > 0:
            logger.info("Cleaned up %d entity_links for retired person chunks", retired_links_cleaned)

        # Step 2: Fetch all active person chunks
        person_chunks, total = self._store.list_chunks(
            domain=Domain.PEOPLE,
            limit=10000,  # Reasonable limit for typical contact volumes
        )

        if not person_chunks:
            logger.info("No person chunks found; entity linking pass is complete")
            return 0

        logger.info("Entity linking pass: found %d person chunks", len(person_chunks))

        # Warn if more person chunks exist beyond the limit
        if total > 10000:
            logger.warning(
                "Person chunks exceed limit (found %d total, fetched 10000); "
                "consider paginating or increasing limit",
                total,
            )

        # Step 3-5: For each person chunk, find matching chunks and write links
        total_links_created = 0
        # (includes cleanup count, not returned separately)
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

                # Build link tuples: (person_chunk_hash, matching_chunk_hash, link_type, confidence)
                links = [
                    (chunk.chunk_hash, matching_hash, "person_appearance", 1.0)
                    for matching_hash in matching_chunk_hashes
                ]

                # Write links (idempotent via UNIQUE constraint)
                new_links = self._store.write_entity_links(links)
                total_links_created += new_links
                if new_links > 0:
                    logger.debug(
                        "Person chunk %s: found %d new links for %d identifier(s)",
                        chunk.chunk_hash,
                        new_links,
                        len(identifiers),
                    )
            except Exception as e:
                logger.error("Error linking person chunk %s: %s", chunk.chunk_hash, e, exc_info=True)
                continue

        logger.info("Entity linking pass complete: created %d new links", total_links_created)
        return total_links_created

    def _extract_identifiers(self, domain_metadata: Optional[dict]) -> list[str]:
        """Extract email and phone identifiers from PeopleMetadata.

        Args:
            domain_metadata: Serialized PeopleMetadata dict from chunk.domain_metadata.

        Returns:
            List of email and phone strings, deduplicated.
        """
        if not domain_metadata:
            return []

        identifiers = set()

        # Extract emails and phones from PeopleMetadata
        if "emails" in domain_metadata:
            emails = domain_metadata.get("emails")
            if isinstance(emails, (list, tuple)):
                identifiers.update(str(e) for e in emails if e)
            elif isinstance(emails, str):
                identifiers.add(emails)

        if "phones" in domain_metadata:
            phones = domain_metadata.get("phones")
            if isinstance(phones, (list, tuple)):
                identifiers.update(str(p) for p in phones if p)
            elif isinstance(phones, str):
                identifiers.add(phones)

        return sorted(list(identifiers))

    def _find_matching_chunks(self, identifiers: list[str]) -> list[str]:
        """Query chunks where domain_metadata contains any of the given identifiers.

        Uses Strategy A: per-identifier SQL scan with json_extract() for scalar fields
        and EXISTS for array fields (recipients, invitees, collaborators).

        Args:
            identifiers: List of email/phone strings to search for.

        Returns:
            List of chunk_hashes from non-people domains where a match was found.
        """
        if not identifiers:
            return []

        cursor = self._store.conn.cursor()
        found_hashes = set()

        # Build WHERE clauses for each field type
        for identifier in identifiers:
            # Build OR conditions for all LINKED_FIELDS
            # Scalar fields: sender, host, author
            # Array fields: recipients, invitees, collaborators
            where_parts = [
                "json_extract(c.domain_metadata, '$.sender') = ?",
                "json_extract(c.domain_metadata, '$.host') = ?",
                "json_extract(c.domain_metadata, '$.author') = ?",
                "EXISTS (SELECT 1 FROM json_each(c.domain_metadata, '$.recipients') WHERE value = ?)",
                "EXISTS (SELECT 1 FROM json_each(c.domain_metadata, '$.invitees') WHERE value = ?)",
                "EXISTS (SELECT 1 FROM json_each(c.domain_metadata, '$.collaborators') WHERE value = ?)",
            ]
            where_clause = " OR ".join(where_parts)

            # Build parameter list: identifier repeated for each field check
            params = [identifier] * len(where_parts) + [Domain.PEOPLE]

            try:
                cursor.execute(
                    f"""
                    SELECT DISTINCT c.chunk_hash
                    FROM chunks c
                    JOIN sources s ON c.source_id = s.source_id
                    WHERE (
                        {where_clause}
                    )
                    AND s.domain != ?
                    AND c.retired_at IS NULL
                    """,
                    params,
                )
                rows = cursor.fetchall()
                for row in rows:
                    found_hashes.add(row[0])
            except Exception as e:
                logger.error("Error querying chunks for identifier %s: %s", identifier, e)
                continue

        return sorted(list(found_hashes))

    def _cleanup_retired_person_links(self) -> int:
        """Clean up entity_links for retired person chunks.

        Queries entity_links for source_chunk_hashes that are no longer active in the
        people domain (i.e., person contacts that were deleted). Deletes those rows.

        Returns:
            Number of rows deleted.
        """
        cursor = self._store.conn.cursor()
        try:
            # Find source_chunk_hashes in entity_links that don't exist as active
            # (non-retired) chunks in the people domain
            cursor.execute(
                """
                SELECT DISTINCT el.source_chunk_hash
                FROM entity_links el
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM chunks c
                    JOIN sources s ON c.source_id = s.source_id
                    WHERE c.chunk_hash = el.source_chunk_hash
                    AND s.domain = ?
                    AND c.retired_at IS NULL
                )
                """,
                (Domain.PEOPLE,),
            )
            retired_chunk_hashes = [row[0] for row in cursor.fetchall()]

            # Delete entity_links for each retired person chunk
            total_deleted = 0
            for chunk_hash in retired_chunk_hashes:
                deleted = self._store.delete_entity_links_for_chunk(chunk_hash)
                total_deleted += deleted

            return total_deleted
        except Exception as e:
            logger.error("Error cleaning up retired person links: %s", e)
            return 0
