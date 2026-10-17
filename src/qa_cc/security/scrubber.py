"""Centralized runtime secret and token scrubber (T-05)."""
from __future__ import annotations

import os
import re
from typing import Any, Iterable, List, Optional, Set


class Scrubber:
    """Scrubs environment secrets, Bearer tokens, JWTs, and sensitive headers from objects."""

    SCRUB_PLACEHOLDER = "[SCRUBBED]"

    DEFAULT_ENV_VARS = [
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
    ]

    SENSITIVE_KEYS: Set[str] = {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "api_key",
        "secret",
        "password",
        "token",
    }

    # JWT pattern: Base64url header.payload.signature
    JWT_PATTERN = re.compile(r"\beyJ[a-zA-Z0-9_\-]{4,}\.[a-zA-Z0-9_\-]{4,}\.[a-zA-Z0-9_\-]+\b")

    # Bearer token pattern
    BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+([a-zA-Z0-9_\-\.\~\+\/=]{4,})")

    def __init__(
        self,
        secret_env_vars: Optional[Iterable[str]] = None,
        additional_secrets: Optional[Iterable[str]] = None,
    ) -> None:
        self._secrets: Set[str] = set()

        vars_to_check = set(self.DEFAULT_ENV_VARS)
        if secret_env_vars:
            vars_to_check.update(secret_env_vars)

        for var in vars_to_check:
            val = os.environ.get(var)
            if val and len(val.strip()) >= 4:
                self._secrets.add(val.strip())

        if additional_secrets:
            for s in additional_secrets:
                if s and len(s.strip()) >= 4:
                    self._secrets.add(s.strip())

    def add_secret(self, secret: str) -> None:
        """Add an exact secret string to be scrubbed."""
        if secret and len(secret.strip()) >= 4:
            self._secrets.add(secret.strip())

    def scrub(self, obj: Any) -> Any:
        """Recursively scrub secrets from strings, dictionaries, lists, and model objects."""
        if hasattr(obj, "model_dump") and callable(obj.model_dump):
            return self.scrub(obj.model_dump())
        if hasattr(obj, "dict") and callable(obj.dict):
            return self.scrub(obj.dict())

        if isinstance(obj, str):
            text = obj
            for sec in self._secrets:
                if sec in text:
                    text = text.replace(sec, self.SCRUB_PLACEHOLDER)

            # Scrub Bearer tokens
            text = self.BEARER_PATTERN.sub(r"Bearer [SCRUBBED]", text)

            # Scrub JWT tokens
            text = self.JWT_PATTERN.sub(self.SCRUB_PLACEHOLDER, text)

            return text

        if isinstance(obj, dict):
            new_dict = {}
            for k, v in obj.items():
                if str(k).lower() in self.SENSITIVE_KEYS:
                    new_dict[k] = self.SCRUB_PLACEHOLDER
                else:
                    new_dict[k] = self.scrub(v)
            return new_dict

        if isinstance(obj, list):
            return [self.scrub(item) for item in obj]

        if isinstance(obj, tuple):
            return tuple(self.scrub(item) for item in obj)

        if isinstance(obj, set):
            return {self.scrub(item) for item in obj}

        return obj
