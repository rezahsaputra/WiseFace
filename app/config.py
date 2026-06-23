"""Application configuration.

All settings are read from environment variables (optionally via a mounted
`.env` file) at process startup. There is no database — credentials live in a
small config list, exactly as Section 3/5 of the PRD specifies.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("facecompare.config")


class Credential:
    """A single internal API caller's credential pair + a friendly label.

    `client` is used purely as a Prometheus metric label so per-caller request
    volume is visible on the dashboard. It is never an employee identifier.
    """

    __slots__ = ("api_key", "api_secret", "client")

    def __init__(self, api_key: str, api_secret: str, client: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = client


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # `model_name` would otherwise clash with pydantic's reserved `model_`
        # namespace and emit a warning at import time.
        protected_namespaces=(),
    )

    # --- Service ---
    app_name: str = "self-hosted-face-compare"
    log_level: str = "INFO"

    # --- Recognition model ---
    # Approved backends only (PRD §9.2): Facenet512 | SFace | Dlib.
    model_name: str = Field(default="Facenet512")
    # Detector backend passed to DeepFace. opencv is fast/light on CPU;
    # retinaface/mtcnn are more accurate but heavier — choose in Milestone 0.
    detector_backend: str = Field(default="opencv")
    align: bool = True

    # --- Calibration (PLACEHOLDER values; replace with Milestone 0 outputs) ---
    # Cosine-similarity -> 0..100 confidence affine mapping. These defaults are
    # intentionally provisional; real calibration comes from the FAR/FRR test
    # set built in Milestone 0. They are NOT interchangeable with Face++'s.
    confidence_scale: float = 100.0
    confidence_offset: float = 0.0
    # Structurally Face++-compatible threshold tiers. Recomputed in Milestone 0.
    threshold_1e_3: float = 62.327
    threshold_1e_4: float = 69.101
    threshold_1e_5: float = 73.975

    # --- Image fetching (image_url inputs) ---
    image_download_timeout_s: float = 5.0
    max_image_bytes: int = 10 * 1024 * 1024  # 10 MB, mirrors Face++ size guard

    # --- Credentials ---
    # Two ways to supply the internal credential list:
    #   1. API_CREDENTIALS  -> inline JSON array of {api_key, api_secret, client}
    #   2. API_CREDENTIALS_FILE -> path to a JSON file with the same array
    api_credentials: Optional[str] = None
    api_credentials_file: Optional[str] = None

    @field_validator("model_name")
    @classmethod
    def _validate_model(cls, v: str) -> str:
        approved = {"Facenet512", "SFace", "Dlib"}
        if v not in approved:
            raise ValueError(
                f"model_name {v!r} is not an approved backend. "
                f"Allowed (PRD §9.2): {sorted(approved)}"
            )
        return v

    def load_credentials(self) -> dict[str, Credential]:
        """Return a map of api_key -> Credential.

        Credentials never appear in logs; only the count is logged.
        """
        raw: Optional[list] = None
        if self.api_credentials_file:
            path = Path(self.api_credentials_file)
            if not path.is_file():
                raise RuntimeError(f"API_CREDENTIALS_FILE not found: {path}")
            raw = json.loads(path.read_text(encoding="utf-8"))
        elif self.api_credentials:
            raw = json.loads(self.api_credentials)

        if not raw:
            raise RuntimeError(
                "No credentials configured. Set API_CREDENTIALS (inline JSON) "
                "or API_CREDENTIALS_FILE (path to JSON)."
            )

        creds: dict[str, Credential] = {}
        for i, entry in enumerate(raw):
            try:
                cred = Credential(
                    api_key=entry["api_key"],
                    api_secret=entry["api_secret"],
                    client=entry.get("client", f"client-{i}"),
                )
            except (KeyError, TypeError) as exc:
                raise RuntimeError(
                    f"Credential entry #{i} is malformed: missing {exc}"
                ) from exc
            creds[cred.api_key] = cred

        logger.info("Loaded %d API credential(s).", len(creds))
        return creds


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
