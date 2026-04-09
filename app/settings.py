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

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    enable_llm_tool_orchestration: bool = True
    openai_orchestrator_model: str = "gpt-5.4"
    openai_orchestrator_reasoning_effort: str = "medium"
    openai_orchestrator_max_steps: int = 6
    openai_orchestrator_max_output_tokens: int = 1800
    openai_orchestrator_timeout_seconds: int = 60

    answer_clinical_question_timeout_seconds: int = 28
    search_trials_total_timeout_seconds: int = 24
    clinical_trials_search_timeout_seconds: int = 12
    clinical_trial_details_timeout_seconds: int = 12
    web_context_timeout_seconds: int = 20
    max_trials_to_enrich_with_publications: int = 5
    per_trial_publication_lookup_timeout_seconds: int = 8

    public_base_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
