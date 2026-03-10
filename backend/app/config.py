from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration read from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://cybersec:changeme_app_db@app-db:5432/cybersec"

    # Redis
    redis_url: str = "redis://app-redis:6379/0"

    # Auth
    jwt_secret_key: str = "changeme_jwt_secret_at_least_32_chars"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # DefectDojo
    defectdojo_url: str = "http://defectdojo-nginx:8080"
    defectdojo_api_key: str = ""

    # Docker
    docker_host: str = "unix:///var/run/docker.sock"

    # Scan defaults
    default_masscan_rate: int = 10000
    default_nuclei_rate_limit: int = 150
    default_amass_timeout: int = 15
    scan_results_base_dir: str = "/results"

    # Celery
    celery_broker_url: str = "redis://app-redis:6379/0"
    celery_result_backend: str = "redis://app-redis:6379/1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
