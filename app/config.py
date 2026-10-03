"""Validated YAML and environment configuration."""

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.exceptions import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"


class ProviderModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["openrouter", "gemini"]
    openrouter: ProviderModelSettings
    gemini: ProviderModelSettings


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    name: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: str


class MockGatewaySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulate_timeout_after_commit: bool = True


class ApplicationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: LLMSettings
    database: DatabaseSettings
    mock_gateway: MockGatewaySettings


def load_settings(settings_path: Path | None = None) -> ApplicationSettings:
    """Load non-secret YAML values and apply environment credential overrides."""
    load_dotenv(PROJECT_ROOT / ".env")
    resolved_path = settings_path or DEFAULT_SETTINGS_PATH

    try:
        raw_settings = yaml.safe_load(resolved_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ConfigurationError(
            f"Could not read settings file '{resolved_path}': {exc}"
        ) from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            f"Settings file '{resolved_path}' is not valid YAML: {exc}"
        ) from exc

    if not isinstance(raw_settings, dict):
        raise ConfigurationError(
            f"Settings file '{resolved_path}' must contain a YAML mapping."
        )

    database_values = dict(raw_settings.get("database") or {})
    environment_overrides = {
        "host": os.getenv("MYSQL_HOST"),
        "port": os.getenv("MYSQL_PORT"),
        "name": os.getenv("MYSQL_DATABASE"),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
    }
    database_values.update(
        {
            key: value
            for key, value in environment_overrides.items()
            if value is not None
        }
    )
    raw_settings["database"] = database_values

    try:
        return ApplicationSettings.model_validate(raw_settings)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid application configuration: {exc}") from exc


def get_llm_api_key(settings: ApplicationSettings) -> str:
    """Return the credential for the selected provider without fallback."""
    variable_name = (
        "OPENROUTER_API_KEY"
        if settings.llm.provider == "openrouter"
        else "GOOGLE_API_KEY"
    )
    api_key = os.getenv(variable_name)
    if not api_key:
        raise ConfigurationError(
            f"Missing required environment variable {variable_name} for "
            f"LLM provider '{settings.llm.provider}'."
        )
    return api_key
