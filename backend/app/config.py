import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "ORX Cold-Outreach Engine"
    API_V1_STR: str = "/api/v1"
    
    # Database Config
    DATABASE_URL: str = "postgresql://aziz@localhost:5432/postgres"  # We'll default to postgres owned by aziz
    
    # Redis & Celery Config
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # API Keys
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    
    # Email / SMTP Config (for Sequencer)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "mock@orx-outreach.ai"
    SMTP_PASSWORD: str = "mock_password"
    
    # IMAP Config (for smart reply stopping)
    IMAP_HOST: str = "imap.gmail.com"
    IMAP_PORT: int = 993
    IMAP_USER: str = "mock@orx-outreach.ai"
    IMAP_PASSWORD: str = "mock_password"
    
    # Notification Integrations
    SLACK_WEBHOOK_URL: str = ""
    
    # General LLM model configuration
    LLM_MODEL: str = "google/gemini-2.5-pro"  # Default high quality model via OpenRouter
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
