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
