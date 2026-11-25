import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    """Read from the environment on every access so tests can override values."""

    @property
    def keys(self) -> list[str]:
        return [k.strip() for k in os.getenv("LLM_API_KEYS", "").split(",") if k.strip()]

    @property
    def model(self) -> str:
        return os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")

    @property
    def database_url(self) -> str:
        return os.getenv("DATABASE_URL", "sqlite:///./app.db")

    @property
    def db_path(self) -> str:
        url = self.database_url
        return url[len("sqlite:///"):] if url.startswith("sqlite:///") else url

    @property
    def allowed_origins(self) -> list[str]:
        raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def simulation_enabled(self) -> bool:
        return _bool("ENABLE_FAILURE_SIMULATION")

    @property
    def cache_type(self) -> str:
        return os.getenv("CACHE_TYPE", "local")  # local (memory) or disk

    @property
    def cache_dir(self) -> str:
        return os.getenv("CACHE_DIR", "/data/cache")

    @property
    def default_system_prompt(self) -> str:
        return os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful, concise assistant.")

    @property
    def mock_llm(self) -> bool:  # tests only: no network calls
        return _bool("MOCK_LLM")


settings = Settings()
