# Project Overview

This is a comprehensive overview of the Context Library project, which provides a robust solution for managing and retrieving document content through semantic search and version control.

## Architecture

The system is built on a modular architecture that separates concerns across multiple layers, each responsible for a specific aspect of content management and retrieval.

### Storage Layer

The storage layer is responsible for persisting document versions, chunks, and vectors. It uses SQLite for transactional integrity and LanceDB for high-performance vector search.

| Component | Type | Purpose |
|-----------|------|---------|
| SQLite | Relational Database | Source versions, chunks, lineage tracking |
| LanceDB | Vector Database | Chunk embeddings, semantic search index |
| Adapter Config | JSON Store | Adapter configurations and metadata |
| Sync Log | Change Tracking | Vector synchronization state |

### Chunking Strategy

Content chunking is a critical component that respects semantic boundaries. Our markdown-aware chunker respects heading hierarchies and code blocks to ensure chunks maintain contextual coherence.

## Getting Started

To quickly get started with the Context Library, follow these steps:

```bash
pip install context-library
```

Create a simple ingest pipeline:

```python
from context_library import IngestionPipeline, DocumentStore
from context_library.domains import NotesDomain

store = DocumentStore(":memory:")
pipeline = IngestionPipeline(store, embedder, differ)
result = pipeline.ingest(adapter, NotesDomain())
print(f"Processed {result['sources_processed']} sources")
```

## API Reference

The main entry point for working with Context Library is the IngestionPipeline class. It orchestrates the full flow from content ingestion to vector storage.

```python
class IngestionPipeline:
    def __init__(self, document_store, embedder, differ):
        """Initialize the pipeline with core components."""
        pass

    def ingest(self, adapter, domain_chunker):
        """Ingest content and return statistics."""
        pass
```

## Configuration

Configuration is managed through adapter configs stored in the database. Each adapter can have custom settings for normalization and chunking behavior.

This section contains configuration details and is relatively short but important for understanding system setup.
