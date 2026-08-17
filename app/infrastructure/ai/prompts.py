"""Versioned prompt loading with path confinement and SHA-256 identity."""

import re
from hashlib import sha256
from pathlib import Path

from app.ports.ai import AIPrompt

_PROMPT_COMPONENT = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


class PromptRepository:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve(strict=True)

    def load(self, name: str, version: str) -> AIPrompt:
        if (
            _PROMPT_COMPONENT.fullmatch(name) is None
            or _PROMPT_COMPONENT.fullmatch(version) is None
        ):
            raise ValueError("prompt name and version are invalid")
        path = (self._root / name / f"v{version}.txt").resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("prompt path escaped its repository") from exc
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError("prompt content is empty")
        return AIPrompt(
            name=name,
            version=version,
            sha256=sha256(content.encode("utf-8")).hexdigest(),
            content=content,
        )
