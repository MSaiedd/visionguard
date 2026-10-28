"""Explicit local identity and hosted persistence configuration."""

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VISION_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///data/visionguard.db"
    data_dir: Path = Path("data/workspace")
    model_dir: Path = Path("artifacts/surface-v1")
    local_tenant: str = "northline"
    auth_mode: Literal["local", "oidc"] = "local"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    local_client_networks: str = "127.0.0.0/8,::1/128"
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    worker_enabled: bool = True
    model_loading: bool = True
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pixels: int = 12_000_000
    max_queued: int = 100

    @model_validator(mode="after")
    def validate_identity(self):
        if self.auth_mode == "oidc" and (
            not all([self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url])
            or not self.oidc_jwks_url.startswith("https://")
        ):
            raise ValueError("Hosted mode requires issuer, audience and HTTPS JWKS URL")
        return self
