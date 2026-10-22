from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


def data_directory() -> Path:
    override = os.environ.get("JARVIS_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "JarvisPT"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str = "pt"
    stt_model: str = "base"
    stt_device: str = Field(default="cpu", pattern="^(cpu|cuda)$")
    microphone: int | None = None
    speaker: int | None = None
    sapi_voice: str | None = None
    endpoint_ms: int = Field(default=450, ge=250, le=1500)
    vad_aggressiveness: int = Field(default=2, ge=0, le=3)
    hands_free: bool = False
    headphones_confirmed: bool = False
    speech_enabled: bool = True
    tts_provider: str = Field(default="sapi", pattern="^(sapi|fish|openai)$")
    online_costs_accepted: bool = False
    fish_model: str | None = None
    fish_voice: str | None = None
    openai_audio_model: str | None = None
    openai_voice: str | None = None
    codex_model: str | None = None
    brain_provider: str = Field(default="codex", pattern="^(codex|ollama)$")
    local_model: str | None = None
    codex_complex_model: str | None = None
    allowed_folders: list[str] = Field(default_factory=list)
    desktop_actions: bool = False
    screen_capture: bool = False
    screen_send: bool = False
    excluded_titles: list[str] = Field(default_factory=list)
    hidden_regions: list[tuple[int, int, int, int]] = Field(default_factory=list)
    monitor_names: dict[str, str] = Field(default_factory=dict)
    reduce_motion: bool = False
    timezone: str = "Europe/Lisbon"


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".jarvis-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def load_settings(root: Path) -> Settings:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "settings.json"
    if path.exists():
        return Settings.model_validate_json(path.read_text(encoding="utf-8"))
    settings = Settings(allowed_folders=[str((root / "documents").resolve())])
    (root / "documents").mkdir(exist_ok=True)
    save_settings(root, settings)
    return settings


def save_settings(root: Path, settings: Settings) -> None:
    atomic_text(root / "settings.json", json.dumps(settings.model_dump(), ensure_ascii=False, indent=2))
