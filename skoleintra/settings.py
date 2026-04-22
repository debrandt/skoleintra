import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from environment variables.

    SKOLEINTRA_* variables provide portal credentials and operating parameters.
    DATABASE_URL is read without a prefix (standard convention).
    """

    model_config = SettingsConfigDict(
        env_prefix="SKOLEINTRA_",
        extra="ignore",
        populate_by_name=True,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Database — no SKOLEINTRA_ prefix, matches standard convention
    database_url: str = Field(
        default="", validation_alias="DATABASE_URL"
    )

    # Notifications — read directly from .env via explicit aliases
    smtp_host: str = Field(default="", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_username: str = Field(default="", validation_alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", validation_alias="SMTP_PASSWORD")
    email_from: str = Field(default="", validation_alias="EMAIL_FROM")
    email_to: str = Field(default="", validation_alias="EMAIL_TO")
    smtp_use_ssl: bool | None = Field(default=None, validation_alias="SMTP_USE_SSL")
    smtp_starttls: bool | None = Field(default=None, validation_alias="SMTP_STARTTLS")

    ntfy_url: str = Field(default="", validation_alias="NTFY_URL")
    ntfy_topic: str = Field(default="", validation_alias="NTFY_TOPIC")
    ntfy_token: str = Field(default="", validation_alias="NTFY_TOKEN")

    # Portal credentials / connection
    hostname: str = ""
    username: str = ""
    password: str = ""
    login_type: str = "uni"  # "uni" or "alm"

    # Local state directory for cookie jar and debug artifacts
    state_dir: str = Field(
        default_factory=lambda: os.path.join(os.path.expanduser("~"), ".skoleintra")
    )


def get_settings() -> Settings:
    return Settings()
