"""Configuration loader for API registrations."""

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """Authentication configuration for an API."""

    type: Literal["bearer", "api_key", "basic", "none"] = "none"
    token: str | None = None
    header_name: str = "Authorization"
    api_key_in: Literal["header", "query"] = "header"


class APISettings(BaseModel):
    """Settings for an API."""

    default_page_size: int = Field(default=20, ge=1, le=100)
    max_batch_size: int = Field(default=50, ge=1, le=100)
    rate_limit_per_second: int = Field(default=5, ge=1, le=100)
    confirm_destructive: bool = True


class APIConfig(BaseModel):
    """Configuration for a single API."""

    name: str
    spec_url: str
    base_url: str
    auth: AuthConfig = Field(default_factory=AuthConfig)
    settings: APISettings = Field(default_factory=APISettings)


class Config(BaseModel):
    """Root configuration containing all registered APIs."""

    apis: list[APIConfig] = []


def resolve_env_vars(value: str | None) -> str | None:
    """
    Resolve environment variable references in a string.

    Values starting with '$' are treated as environment variable references.
    Example: "$PETSTORE_KEY" -> os.environ.get("PETSTORE_KEY")
    """
    if value is None:
        return None

    if value.startswith("$"):
        env_var = value[1:]
        return os.environ.get(env_var, "")

    return value


def load_config(path: str | Path) -> Config:
    """
    Load configuration from a JSON file.

    Args:
        path: Path to the configuration JSON file.

    Returns:
        Config object with all registered APIs.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
        json.JSONDecodeError: If the file is not valid JSON.
        pydantic.ValidationError: If the config doesn't match the schema.
    """
    path = Path(path)

    with open(path) as f:
        data = json.load(f)

    config = Config.model_validate(data)

    # Resolve environment variables in auth tokens
    for api in config.apis:
        if api.auth.token:
            api.auth.token = resolve_env_vars(api.auth.token)

    return config
