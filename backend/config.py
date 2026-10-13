"""Validated settings; importing this module never reads dotenv or opens MongoDB."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import sys
from typing import Mapping
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values


class ConfigurationError(ValueError):
    """Safe configuration errors: never include variable values or credentials."""


@dataclass(frozen=True)
class Settings:
    app_env: str
    mongo_url: str = field(repr=False)
    db_name: str
    cors_origins: tuple[str, ...]
    log_level: str
    expected_financial_environment_id: str | None = None
    shared_obligations_enabled: bool = False
    history_keys_write_enabled: bool = False
    history_keys_generation: int | None = None


def settings_from_mapping(values: Mapping[str, str]) -> Settings:
    env = values.get("APP_ENV", "development")
    if env not in {"development", "test", "production"}:
        raise ConfigurationError("APP_ENV must be development, test or production.")
    uri = values.get("MONGO_URL", "").strip()
    try:
        parsed = urlsplit(uri)
        valid_uri = parsed.scheme in {"mongodb", "mongodb+srv"} and bool(parsed.hostname) and not parsed.fragment
    except ValueError:
        valid_uri = False
    if not valid_uri:
        raise ConfigurationError("MONGO_URL must be a valid MongoDB connection URI.")
    name = values.get("DB_NAME", "").strip()
    if not name or len(name.encode()) > 63 or re.search(r'[ /\\.\x00"$:*?<>|]', name):
        raise ConfigurationError("DB_NAME must be a valid explicit database name.")
    if values.get("MONEYFLOW_LOCAL_MODE") == "1":
        # Validate the final configuration, including external process overrides.
        if env != "development":
            raise ConfigurationError("Local mode requires APP_ENV=development.")
        if parsed.scheme != "mongodb" or parsed.netloc != "127.0.0.1:27018":
            raise ConfigurationError("Local mode requires MongoDB at 127.0.0.1:27018 only.")
        if name != "development_local_finanzas" or parsed.path not in {"", "/", "/development_local_finanzas"}:
            raise ConfigurationError("Local mode requires DB_NAME=development_local_finanzas and a matching URI database.")
        if parse_qs(parsed.query, keep_blank_values=True) != {
            "replicaSet": ["app_finanzas_dev_rs"], "directConnection": ["true"]
        }:
            raise ConfigurationError("Local mode requires replicaSet=app_finanzas_dev_rs and directConnection=true without additional options.")
    origins = tuple(x.strip() for x in values.get("CORS_ORIGINS", "*" if env == "development" else "").split(",") if x.strip())
    if not origins:
        raise ConfigurationError("CORS_ORIGINS must specify at least one origin.")
    for origin in origins:
        if origin == "*" and env == "development":
            continue
        try:
            u = urlsplit(origin)
            valid = u.scheme in {"http", "https"} and bool(u.hostname) and not u.username and not u.password and u.path in {"", "/"} and not u.query and not u.fragment and "*" not in origin
            _ = u.port
        except ValueError:
            valid = False
        if not valid:
            raise ConfigurationError("CORS_ORIGINS must contain explicit HTTP origins; wildcard is development-only.")
    level = values.get("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError("LOG_LEVEL is invalid.")
    test_name = bool(re.search(r"(^|[^a-z0-9])test", name.lower())) or name.lower().endswith("test")
    if env == "production" and test_name:
        raise ConfigurationError("Production DB_NAME must not identify a test database.")
    if env == "test":
        # A strict single-host allowlist excludes Atlas, SRV and mixed-host URIs.
        authority = parsed.netloc.rsplit("@", 1)[-1]
        if parsed.scheme != "mongodb" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or "," in authority:
            raise ConfigurationError("Test MONGO_URL must target a single loopback host.")
        try:
            _ = parsed.port
        except ValueError:
            raise ConfigurationError("Test MONGO_URL port is invalid.") from None
        if parsed.username or parsed.password or set(parse_qs(parsed.query)) - {"replicaSet", "directConnection"}:
            raise ConfigurationError("Test URI must not contain credentials or unsupported options.")
        if not re.fullmatch(r"test_[a-zA-Z0-9_-]+", name):
            raise ConfigurationError("Test DB_NAME must begin with test_.")
        if parsed.path not in {"", "/", "/" + name}:
            raise ConfigurationError("Test URI database must match DB_NAME.")
    # Validate this optional pin only when the new protected API is used.
    # Legacy startup and payments remain compatible even without provisioning.
    expected = values.get("MONEYFLOW_EXPECTED_ENVIRONMENT_ID", "").strip() or None
    shared_flag = values.get("MONEYFLOW_SHARED_OBLIGATIONS_ENABLED", "0")
    if shared_flag not in ("0", "1"):
        raise ConfigurationError("MONEYFLOW_SHARED_OBLIGATIONS_ENABLED must be 0 or 1.")
    history_flag = values.get("MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED", "0")
    if history_flag not in ("0", "1"):
        raise ConfigurationError("MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED must be 0 or 1.")
    generation_text = values.get("MONEYFLOW_HISTORY_KEYS_GENERATION", "")
    generation = None
    if generation_text:
        if not re.fullmatch(r"[1-9][0-9]{0,9}", generation_text) or int(generation_text) > 2147483647:
            raise ConfigurationError("MONEYFLOW_HISTORY_KEYS_GENERATION must be a positive BSON int32.")
        generation = int(generation_text)
    if history_flag == "1" and generation is None:
        raise ConfigurationError("History key writes require an explicit generation.")
    return Settings(env, uri, name, origins, level, expected, shared_flag == "1", history_flag == "1", generation)


def load_settings(environ=None, *, dotenv_path=None, testing=None) -> Settings:
    """Process variables override dotenv; tests never load the real dotenv file."""
    values = dict(os.environ if environ is None else environ)
    if testing is None:
        testing = "pytest" in sys.modules or "unittest" in sys.modules or "PYTEST_CURRENT_TEST" in values
    if testing and values.get("APP_ENV") != "test":
        raise ConfigurationError("Test execution requires explicit APP_ENV=test.")
    if values.get("APP_ENV") != "test":
        path = Path(dotenv_path) if dotenv_path is not None else Path(__file__).with_name(".env")
        values = {**{k: v for k, v in dotenv_values(path).items() if v is not None}, **values}
    return settings_from_mapping(values)
