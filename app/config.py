from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = "development"
    log_level: str = "info"

    # RapidAPI
    rapidapi_proxy_secret: str = ""

    # Cache
    cache_max_size: int = 4000
    cache_ttl_seconds: int = 3600

    # Fetcher
    fetch_timeout_seconds: int = 10
    max_response_bytes: int = 5 * 1024 * 1024  # 5MB

    # Limits
    max_urls_per_request: int = 10
    max_request_tokens: int = 128_000

    # Tier configs: tier_name -> {max_urls, max_tokens, playwright}
    @property
    def tiers(self) -> dict:
        return {
            "BASIC": {"max_urls": 3, "max_tokens": 16_000, "playwright": True},
            "PRO": {"max_urls": 10, "max_tokens": 64_000, "playwright": True},
            "ULTRA": {"max_urls": 10, "max_tokens": 128_000, "playwright": True},
            "MEGA": {"max_urls": 10, "max_tokens": 128_000, "playwright": True},
            # Free tier / unknown
            "default": {"max_urls": 1, "max_tokens": 4_000, "playwright": False},
        }

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
