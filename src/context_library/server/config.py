"""Server configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """Configuration for the context-library server.

    All settings can be overridden via environment variables prefixed with CTX_.
    For example, CTX_SQLITE_DB_PATH=/data/documents.db.
    """

    model_config = SettingsConfigDict(env_prefix="CTX_", env_file=".env", env_file_encoding="utf-8")

    # Storage paths
    sqlite_db_path: str = "/data/sqlite/documents.db"
    chromadb_path: str = "/data/chromadb"

    # Embedding model
    embedding_model: str = "all-MiniLM-L6-v2"

    # Reranker (optional)
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    enable_reranker: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Webhook authentication
    webhook_secret: str = ""

    # context-helpers bridge service
    helper_url: str = ""
    helper_api_key: str = ""
    helper_filesystem_enabled: bool = False
    helper_filesystem_timeout: float = 300.0  # seconds; large dirs can be slow to start streaming
    helper_contacts_timeout: float = 120.0   # seconds; initial full export can be slow
    helper_pull_poll_interval_sec: int = 300   # seconds between background polls of PULL adapters
    helper_obsidian_enabled: bool = False
    helper_oura_enabled: bool = False

    # YouTube adapters (standalone — no helper bridge required)
    youtube_enabled: bool = False
    youtube_takeout_path: str = ""          # Path to Google Takeout watch-history.json
    youtube_account_id: str = "default"
    youtube_transcript_languages: str = "en"  # Comma-separated language preference order
