"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All settings are read from environment variables or a .env file."""

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./memory_passport.db"

    # --- JWT Auth ---
    jwt_secret_key: str = "change-me-to-a-random-secret-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # --- LLM Provider (OpenAI-compatible) ---
    llm_provider: str = "qwen"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen-plus"

    # --- Embedding Provider (OpenAI-compatible) ---
    embedding_provider: str = "dashscope"
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    embedding_model: str = "qwen3.7-text-embedding-flash"
    embedding_dimensions: int = 1024

    def get_embedding_api_key(self) -> str:
        """Return embedding API key, falling back to LLM / DashScope key."""
        return self.embedding_api_key or self.llm_api_key

    # --- CORS ---
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- MCP ---
    mcp_api_key: str = "mcp-change-me-to-a-random-key"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
