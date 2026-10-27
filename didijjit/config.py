"""Ustawienia z config.toml (albo domyślne z config.example.toml)."""
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("DIDIJJIT_CONFIG", ROOT / "config.toml"))
EXAMPLE_PATH = ROOT / "config.example.toml"


@dataclass
class Config:
    categories: list[str] = field(default_factory=lambda: ["ai", "php", "python"])
    cities: list[str] = field(default_factory=lambda: ["trojmiasto"])
    remote: bool = True
    only_poland: bool = True
    experience: list[str] = field(default_factory=list)
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    exclude_companies: list[str] = field(default_factory=list)
    browsers: list[str] = field(default_factory=lambda: ["brave", "chrome", "edge", "chromium", "opera", "vivaldi", "firefox"])
    extra_paths: list[str] = field(default_factory=list)
    port: int = 8765
    source: str = "domyślne"


def load(path: Path | None = None) -> Config:
    path = path or (CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
    if not path.exists():
        return Config()
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    jj, flt, hist, srv = (raw.get(k, {}) for k in ("justjoin", "filters", "history", "server"))
    merged = {**jj, **flt, **hist, **srv}
    known = {k: v for k, v in merged.items() if k in Config.__dataclass_fields__}
    return Config(**known, source=str(path.name))
