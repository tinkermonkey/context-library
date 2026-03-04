"""Expected structure for fixture file differences.

Documents the semantic changes between sample_initial.md and sample_modified.md.

Changes in sample_modified.md:
1. MODIFIED: "### Storage Layer" section - paragraph content has been changed
   From: "The storage layer is responsible for persisting document versions, chunks, and vectors..."
   To: "The storage layer is responsible for persisting all data artifacts reliably..."

2. ADDED: "## Contributing" section (new H2 section with bullet points and text)
   Lines 24-33 in sample_modified.md (between "### Chunking Strategy" and "## API Reference")

3. REMOVED: "## Getting Started" section (H2 with code blocks)
   Lines 24-42 in sample_initial.md (between "### Chunking Strategy" and "## API Reference")

Unchanged sections:
- "# Project Overview" (lines 1-3)
- "## Architecture" (lines 5-7)
- "### Storage Layer" heading with table (heading + table structure, but paragraph content differs)
- "### Chunking Strategy" (lines 20-22)
- "## API Reference" (lines 44-57 initial, 35-48 modified)
- "## Configuration" (lines 59-63 initial, 50-54 modified)
"""


def get_expected_changes(initial_chunks, modified_chunks):
    """Compute expected diff between initial and modified chunk lists.

    Args:
        initial_chunks: List of chunks from sample_initial.md
        modified_chunks: List of chunks from sample_modified.md

    Returns:
        Dict with lists of added_hashes, removed_hashes, unchanged_hashes
    """
    initial_hashes = {chunk.hash for chunk in initial_chunks}
    modified_hashes = {chunk.hash for chunk in modified_chunks}

    # A chunk is unchanged if hash is present in both versions
    unchanged_hashes = initial_hashes & modified_hashes
    added_hashes = modified_hashes - initial_hashes
    removed_hashes = initial_hashes - modified_hashes

    return {
        "added_hashes": sorted(list(added_hashes)),
        "removed_hashes": sorted(list(removed_hashes)),
        "unchanged_hashes": sorted(list(unchanged_hashes)),
    }
