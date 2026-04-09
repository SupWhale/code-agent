"""
CLI 설정 관리 — ~/.config/code-agent/config.json
"""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "code-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "server_url": "http://localhost:8000",
    "session_id": None,
    "workspace_path": None,
}


def load() -> dict:
    if CONFIG_FILE.exists():
        try:
            return {**DEFAULTS, **json.loads(CONFIG_FILE.read_text())}
        except Exception:
            pass
    return dict(DEFAULTS)


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def get(key: str):
    return load().get(key)


def set_value(key: str, value) -> None:
    cfg = load()
    cfg[key] = value
    save(cfg)
