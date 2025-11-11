thonimport json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False
    return logger

def load_settings(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Settings file not found at {path}")

    with path.open("r", encoding="utf-8") as f:
        try:
            settings = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in settings file {path}: {exc}") from exc

    if not isinstance(settings, dict):
        raise ValueError("Settings file must contain a JSON object at the top level.")

    return settings

def convert_unix_to_iso(unix_ts: int) -> str:
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.isoformat()

def normalize_hashtag(hashtag: str) -> str:
    return hashtag.lstrip("#").strip()