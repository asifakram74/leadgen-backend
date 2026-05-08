from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
import os

class Settings(BaseSettings):
    # --- ADD THIS LINE ---
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    # SMTP Settings
    MAIL_USERNAME: str = "your_email@gmail.com"
    MAIL_PASSWORD: str = "your_app_password"
    MAIL_FROM: str = "your_email@gmail.com"
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_FROM_NAME: str = "LeadStation Pro"
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    USE_CREDENTIALS: bool = True
    VALIDATE_CERTS: bool = True

    # Application Settings
    @property
    def get_cors_origins(self) -> List[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    # Will be overridden by the .env file. This is just a dev fallback.
    SECRET_KEY: str = "yoursupersecretkeyhere"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200
    
    # AI Configuration
    DEEPSEEK_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)
settings = Settings()