import os
from pydantic_settings import BaseSettings
from typing import List, Optional

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE_PATH = os.path.join(BACKEND_DIR, ".env")

class Settings(BaseSettings):
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Database
    database_url: Optional[str] = "sqlite:///./data_monitoring.db"
    db_host: Optional[str] = None
    db_port: Optional[int] = 5432
    db_name: Optional[str] = None
    db_user: Optional[str] = None
    db_password: Optional[str] = None

    # JWT Authentication
    jwt_secret: str = "dmp-enterprise-secret-key-6f81a7d890b2401f8d93e8271a3962b5"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 7

    # CORS
    cors_origins: str = "http://localhost:4321,http://127.0.0.1:4321,http://localhost:3000,http://127.0.0.1:3000"

    @property
    def parsed_cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            if self.database_url.startswith("sqlite:///./"):
                # Ensure absolute sqlite path relative to backend dir
                db_filename = self.database_url.replace("sqlite:///./", "")
                abs_db_path = os.path.join(BACKEND_DIR, db_filename)
                return f"sqlite:///{abs_db_path.replace(os.sep, '/')}"
            return self.database_url
        if self.db_host and self.db_user and self.db_password and self.db_name:
            import urllib.parse
            safe_pass = urllib.parse.quote_plus(self.db_password)
            return f"postgresql://{self.db_user}:{safe_pass}@{self.db_host}:{self.db_port}/{self.db_name}"
        abs_db_path = os.path.join(BACKEND_DIR, "data_monitoring.db")
        return f"sqlite:///{abs_db_path.replace(os.sep, '/')}"

    class Config:
        env_file = ENV_FILE_PATH
        extra = "ignore"

settings = Settings()
