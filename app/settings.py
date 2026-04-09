from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "clinical-intel-mcp"
    app_env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    request_timeout_seconds: int = 25
    user_agent: str = "clinical-intel-mcp/0.2.0"

    google_cloud_project: str | None = None
    google_cloud_location: str = "global"
    google_genai_use_vertexai: bool = True
    vertex_gemini_model: str = "gemini-2.5-flash"
    enable_vertex_web_search: bool = True

    public_base_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()