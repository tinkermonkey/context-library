"""FastAPI application factory with lifespan management."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from context_library.adapters.base import BaseAdapter
from context_library.domains.registry import get_domain_chunker
from context_library.core.differ import Differ
from context_library.server.helper_health import HelperHealthCache
from context_library.core.embedder import Embedder
from context_library.core.pipeline import IngestionPipeline
from context_library.scheduler.poller import Poller
from context_library.server.config import ServerConfig
from context_library.server.routes import adapters, chunks, health, ingest, retrieve, sources, stats
from context_library.storage.chromadb_store import ChromaDBVectorStore
from context_library.storage.document_store import DocumentStore

logging.getLogger("context_library").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = ServerConfig()

    # Ensure parent directory exists for SQLite DB
    db_path = Path(config.sqlite_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize components in dependency order
    document_store = DocumentStore(config.sqlite_db_path, check_same_thread=False)
    embedder = Embedder(config.embedding_model)
    differ = Differ()
    vector_store = ChromaDBVectorStore(config.chromadb_path)
    pipeline = IngestionPipeline(document_store, embedder, differ, vector_store)

    reranker = None
    if config.enable_reranker:
        from context_library.retrieval.reranker import Reranker

        reranker = Reranker(config.reranker_model)

    # Build helper adapters if the helper is configured
    helper_adapters: list[BaseAdapter] = []
    if config.helper_url and config.helper_api_key:
        # AppleRemindersAdapter
        try:
            from context_library.adapters.apple_reminders import AppleRemindersAdapter
            helper_adapters.append(AppleRemindersAdapter(api_url=config.helper_url, api_key=config.helper_api_key))
        except ImportError as e:
            logger.warning("AppleRemindersAdapter not available (missing dependency): %s", e)
        except ValueError as e:
            logger.warning(
                "AppleRemindersAdapter not available (invalid configuration): %s. "
                "Ensure CTX_HELPER_API_KEY is set when helper adapters are enabled",
                e
            )

        # AppleHealthAdapter
        try:
            from context_library.adapters.apple_health import AppleHealthAdapter
            helper_adapters.append(AppleHealthAdapter(api_url=config.helper_url, api_key=config.helper_api_key))
        except ImportError as e:
            logger.warning("AppleHealthAdapter not available (missing dependency): %s", e)
        except ValueError as e:
            logger.warning(
                "AppleHealthAdapter not available (invalid configuration): %s. "
                "Ensure CTX_HELPER_API_KEY is set when helper adapters are enabled",
                e
            )

        # AppleiMessageAdapter
        try:
            from context_library.adapters.apple_imessage import AppleiMessageAdapter
            helper_adapters.append(AppleiMessageAdapter(api_url=config.helper_url, api_key=config.helper_api_key))
        except ImportError as e:
            logger.warning("AppleiMessageAdapter not available (missing dependency): %s", e)
        except ValueError as e:
            logger.warning(
                "AppleiMessageAdapter not available (invalid configuration): %s. "
                "Ensure CTX_HELPER_API_KEY is set when helper adapters are enabled",
                e
            )

        # AppleNotesAdapter
        try:
            from context_library.adapters.apple_notes import AppleNotesAdapter
            helper_adapters.append(AppleNotesAdapter(api_url=config.helper_url, api_key=config.helper_api_key))
        except ImportError as e:
            logger.warning("AppleNotesAdapter not available (missing dependency): %s", e)
        except ValueError as e:
            logger.warning(
                "AppleNotesAdapter not available (invalid configuration): %s. "
                "Ensure CTX_HELPER_API_KEY is set when helper adapters are enabled",
                e
            )

        # AppleMusicLibraryAdapter (track catalog → documents domain, play events → events domain)
        try:
            from context_library.adapters.apple_music_library import AppleMusicLibraryAdapter
            helper_adapters.append(AppleMusicLibraryAdapter(api_url=config.helper_url, api_key=config.helper_api_key))
        except ImportError as e:
            logger.warning("AppleMusicLibraryAdapter not available (missing dependency): %s", e)
        except ValueError as e:
            logger.warning(
                "AppleMusicLibraryAdapter not available (invalid configuration): %s. "
                "Ensure CTX_HELPER_API_KEY is set when helper adapters are enabled",
                e
            )

        # AppleContactsAdapter
        try:
            from context_library.adapters.apple_contacts import AppleContactsAdapter
            helper_adapters.append(AppleContactsAdapter(api_url=config.helper_url, api_key=config.helper_api_key, timeout=config.helper_contacts_timeout))
        except ImportError as e:
            logger.warning("AppleContactsAdapter not available (missing dependency): %s", e)
        except ValueError as e:
            logger.warning(
                "AppleContactsAdapter not available (invalid configuration): %s. "
                "Ensure CTX_HELPER_API_KEY is set when helper adapters are enabled",
                e
            )

        if config.helper_filesystem_enabled:
            try:
                from context_library.adapters.filesystem_helper import FilesystemHelperAdapter
                helper_adapters.append(FilesystemHelperAdapter(api_url=config.helper_url, api_key=config.helper_api_key, timeout=config.helper_filesystem_timeout))
            except ImportError as e:
                logger.warning("FilesystemHelperAdapter not available (missing dependency): %s", e)

        # ObsidianHelperAdapter
        try:
            from context_library.adapters.obsidian_helper import ObsidianHelperAdapter
            helper_adapters.append(ObsidianHelperAdapter(api_url=config.helper_url, api_key=config.helper_api_key))
        except ImportError as e:
            logger.warning("ObsidianHelperAdapter not available (missing dependency): %s", e)
        except ValueError as e:
            logger.warning(
                "ObsidianHelperAdapter not available (invalid configuration): %s. "
                "Ensure CTX_HELPER_API_KEY is set when helper adapters are enabled",
                e
            )

        # OuraAdapter (only if enabled)
        if config.helper_oura_enabled:
            try:
                from context_library.adapters.oura import OuraAdapter
                helper_adapters.append(OuraAdapter(api_url=config.helper_url, api_key=config.helper_api_key))
            except ImportError as e:
                logger.warning("OuraAdapter not available (missing dependency): %s", e)
            except ValueError as e:
                logger.warning(
                    "OuraAdapter not available (invalid configuration): %s. "
                    "Ensure CTX_HELPER_API_KEY is set when helper adapters are enabled",
                    e
                )

        # YouTube watch history + transcripts (requires helper bridge with youtube collector enabled)
        if config.youtube_enabled:
            try:
                from context_library.adapters.youtube_watch_history import YouTubeWatchHistoryAdapter
                from context_library.adapters.youtube_transcripts import YouTubeTranscriptAdapter

                languages = [lang.strip() for lang in config.youtube_transcript_languages.split(",") if lang.strip()]
                watch_adapter = YouTubeWatchHistoryAdapter(
                    api_url=config.helper_url,
                    api_key=config.helper_api_key,
                    account_id=config.youtube_account_id,
                )
                transcript_adapter = YouTubeTranscriptAdapter(
                    document_store=document_store,
                    watch_history_adapter_id=watch_adapter.adapter_id,
                    account_id=config.youtube_account_id,
                    languages=languages or ["en"],
                )
                helper_adapters.extend([watch_adapter, transcript_adapter])
            except ImportError as exc:
                logger.warning("YouTube adapters not available (missing dependency): %s", exc)
            except ValueError as exc:
                logger.warning("YouTube adapters not available (invalid configuration): %s", exc)

        if helper_adapters:
            logger.info("Helper adapters configured (%d adapters, url=%s)", len(helper_adapters), config.helper_url)

    # Build helper health cache (probes helper /health on demand, TTL 30s)
    helper_health_cache = None
    if config.helper_url and config.helper_api_key and helper_adapters:
        helper_health_cache = HelperHealthCache(
            helper_url=config.helper_url,
            api_key=config.helper_api_key,
            adapters=helper_adapters,
        )

    # Store on app.state for route access
    app.state.config = config
    app.state.document_store = document_store
    app.state.embedder = embedder
    app.state.vector_store = vector_store
    app.state.pipeline = pipeline
    app.state.reranker = reranker
    app.state.helper_adapters = helper_adapters
    app.state.helper_health_cache = helper_health_cache

    logger.info(
        "Server started (model=%s, dim=%d, vectors=%d)",
        embedder.model_id,
        embedder.dimension,
        vector_store.count(),
    )

    # Create and start the Poller for all adapters (helper + webhook).
    # The poller is responsible for periodic ingestion of PULL-strategy sources and
    # also provides trigger_immediate_ingest() for manual reset flows.
    pull_adapters = [a for a in helper_adapters if getattr(a, "background_poll", False)]
    poller = Poller(pipeline, document_store, tick_interval=config.helper_pull_poll_interval_sec)
    for adapter in pull_adapters:
        domain_chunker = get_domain_chunker(adapter.domain)
        poller.register(adapter, domain_chunker)

    if pull_adapters:
        logger.warning(
            "Registered %d PULL adapter(s) with poller: %s",
            len(pull_adapters),
            [a.adapter_id for a in pull_adapters],
        )
        poller.start()

    # Store poller on app.state for route access (e.g., POST /adapters/{id}/reset)
    app.state.poller = poller

    yield

    poller.stop()
    document_store.close()
    logger.info("Server stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="context-library", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(retrieve.router)
    app.include_router(adapters.router)
    app.include_router(sources.router)
    app.include_router(chunks.router)
    app.include_router(stats.router)

    # Mount static SPA if built assets exist
    ui_dist = Path(__file__).parent.parent.parent.parent / "ui" / "dist"
    if ui_dist.exists():
        # Serve assets (JS, CSS, images) from /assets/
        app.mount("/assets", StaticFiles(directory=ui_dist / "assets"), name="assets")

        # Serve root-level static files (favicon.svg, robots.txt, etc.)
        @app.get("/favicon.svg")
        async def favicon():
            favicon_path = ui_dist / "favicon.svg"
            if favicon_path.exists():
                return FileResponse(favicon_path, media_type="image/svg+xml")
            raise HTTPException(status_code=404, detail="Not Found")

        # SPA fallback: unmatched GET requests for client-side routes return index.html
        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            # Whitelist of known client-side routes. Only these routes (and their subpaths)
            # get the SPA fallback. Any other path is assumed to be an API route attempt
            # and returns 404 JSON instead of HTML to avoid confusing API clients with HTML.
            # Client-side route prefixes (from the React Router configuration in ui/src/router.tsx)
            client_prefixes = ("browser", "search")

            # Check if this is a known client-side route
            is_client_route = (
                full_path == ""  # root path (/) is the dashboard
                or any(full_path == prefix or full_path.startswith(prefix + "/") for prefix in client_prefixes)
            )

            # If not a known client route, return 404 to protect API clients from getting HTML
            if not is_client_route:
                raise HTTPException(status_code=404, detail="Not Found")

            return FileResponse(ui_dist / "index.html")

    return app


app = create_app()
