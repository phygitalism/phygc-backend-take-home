from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration. Every field can be overridden with a GP_* env var."""

    model_config = SettingsConfigDict(env_prefix="GP_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://genpipe:genpipe@localhost:5432/genpipe"
    broker_url: str = "amqp://guest:guest@localhost:5672//"
    redis_url: str = "redis://localhost:6379/0"

    # Upstream generation provider ("Acme Generative API", see docs/provider_api.md)
    provider_base_url: str = "http://localhost:9000"
    provider_api_key: str = "dev-provider-key"
    provider_webhook_secret: str = "dev-webhook-secret"

    # Base URL the provider uses to reach us with webhooks
    public_base_url: str = "http://localhost:8000"

    submit_rate_limit_per_minute: int = 60
    max_provider_attempts: int = 5
    # A job that stays in "processing" longer than this is considered lost
    job_timeout_seconds: int = 900
    models_cache_ttl_seconds: int = 300

    # Run Celery tasks inline (used by the test suite)
    celery_always_eager: bool = False


settings = Settings()
