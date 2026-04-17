from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
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
    FRONTEND_URL: str = "https://leadfront.onlinetoolpot.com"
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,https://leadfront.onlinetoolpot.com,http://leadfront.onlinetoolpot.com,https://leadgenfront.onlinetoolpot.com,http://leadgenfront.onlinetoolpot.com"
    SECRET_KEY: str = "yoursupersecretkeyhere"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
