"""Gateway settings: the Lambda environment set by template.yaml, and the styles in styles.json."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from gateway.generation import Style

__all__ = ["Settings", "load_settings"]

STYLES_FILE = Path(__file__).with_name("styles.json")


@dataclass(frozen=True)
class Settings:
    styles: dict[str, Style]
    fal_key_secret_id: str
    usage_table: str
    images_per_key_per_day: int
    images_per_day: int


def load_settings() -> Settings:
    """Read the settings; a missing variable raises KeyError naming it."""
    env = os.environ
    return Settings(
        styles=_styles(),
        fal_key_secret_id=env["FAL_KEY_SECRET_ID"],
        usage_table=env["USAGE_TABLE"],
        images_per_key_per_day=int(env["IMAGES_PER_KEY_PER_DAY"]),
        images_per_day=int(env["IMAGES_PER_DAY"]),
    )


def _styles() -> dict[str, Style]:
    entries = json.loads(STYLES_FILE.read_text(encoding="utf-8"))
    styles = {name: Style(name=name, lora_url=entry["lora_url"], phrase=entry["phrase"]) for name, entry in entries.items()}
    if not styles or not all(style.lora_url.startswith("https://") and style.phrase for style in styles.values()):
        raise ValueError(f"{STYLES_FILE.name} must give each style an https lora_url and a phrase")
    return styles
