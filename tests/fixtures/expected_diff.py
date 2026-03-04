"""
Expected DiffResult outcomes for fixture files.

This module documents the expected changes when comparing sample_initial.md to sample_modified.md.

Changes in sample_modified.md:
1. MODIFIED: "### Storage Layer" section - the paragraph content has been changed
2. ADDED: "## Contributing" section (new H2 heading with content)
3. REMOVED: "## Getting Started" section (H2 heading with code examples removed)

The other sections (Overview, Architecture, Chunking Strategy, API Reference, Configuration) remain unchanged.
"""

# Expected chunk hashes that should be in sample_initial.md (these are the hashes that will differ)
# These are deterministic - computed by the NotesDomain chunker with whitespace normalization

EXPECTED_CHANGES = {
    "modified_chunks": [
        # The "### Storage Layer" section content changed
        # The chunker will create a new hash for this section's chunk
    ],
    "added_chunks": [
        # "## Contributing" is a new H2 section with content
    ],
    "removed_chunks": [
        # "## Getting Started" with its code blocks is removed
    ],
    "unchanged_chunks": [
        # The following sections stay the same:
        # "# Project Overview" (intro)
        # "## Architecture" (intro)
        # "### Chunking Strategy"
        # "## API Reference" with code block
        # "## Configuration"
    ],
}

# NOTE: The actual chunk hashes are computed by chunking the markdown files using NotesDomain.
# Tests will compute these at runtime using the actual chunker and embedder.
# This module documents the semantic structure of expected changes for validation purposes.
