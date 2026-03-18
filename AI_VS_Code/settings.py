"""
config/settings.py
Centralised configuration — reads from .env / Azure Key Vault in production.
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env (no-op if already set via environment / Key Vault injection)
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    db_type: str = field(default_factory=lambda: os.getenv("DB_TYPE", "sqlite"))
    sqlite_path: str = field(default_factory=lambda: os.getenv("SQLITE_DB_PATH", "./data/queries.db"))
    mysql_host: str = field(default_factory=lambda: os.getenv("MYSQL_HOST", ""))
    mysql_port: int = field(default_factory=lambda: int(os.getenv("MYSQL_PORT", "3306")))
    mysql_database: str = field(default_factory=lambda: os.getenv("MYSQL_DATABASE", "voiceagent_db"))
    mysql_user: str = field(default_factory=lambda: os.getenv("MYSQL_USER", ""))
    mysql_password: str = field(default_factory=lambda: os.getenv("MYSQL_PASSWORD", ""))

    @property
    def connection_url(self) -> str:
        if self.db_type == "mysql":
            return (
                f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
                f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            )
        # Default: SQLite (free, zero-setup, perfect for demo/dev)
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.sqlite_path}"


@dataclass
class GoogleConfig:
    service_account_json: str = field(
        default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "./config/google_service_account.json")
    )
    sheet_id: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEET_ID", ""))
    sheet_name: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEET_NAME", "CustomerQueries"))


@dataclass
class EmailConfig:
    sendgrid_api_key: str = field(default_factory=lambda: os.getenv("SENDGRID_API_KEY", ""))
    from_email: str = field(default_factory=lambda: os.getenv("EMAIL_FROM", "agent@yourcompany.com"))
    from_name: str = field(default_factory=lambda: os.getenv("EMAIL_FROM_NAME", "AI Voice Agent"))
    product_dept_email: str = field(default_factory=lambda: os.getenv("PRODUCT_DEPT_EMAIL", "product@yourcompany.com"))
    payment_dept_email: str = field(default_factory=lambda: os.getenv("PAYMENT_DEPT_EMAIL", "payments@yourcompany.com"))
    summary_hour: int = field(default_factory=lambda: int(os.getenv("SUMMARY_SCHEDULE_HOUR", "9")))
    summary_minute: int = field(default_factory=lambda: int(os.getenv("SUMMARY_SCHEDULE_MINUTE", "0")))


@dataclass
class AppConfig:
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    app_title: str = field(default_factory=lambda: os.getenv("APP_TITLE", "AI Voice Agent"))
    company_name: str = field(default_factory=lambda: os.getenv("COMPANY_NAME", "Your Company"))
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    email: EmailConfig = field(default_factory=EmailConfig)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


# Singleton
settings = AppConfig()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
