"""Resolve and validate the application config.ini path."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Directory that owns config.ini (app/ in source, exe folder when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolve_config_path(config_arg: str = "config.ini") -> Path:
    """
    Always return an absolute path to config.ini.

    Search order:
      1. Absolute path from --config
      2. Next to the .exe (frozen)
      3. app/config.ini (source)
      4. Project root config.ini (fallback)
    """
    if config_arg and os.path.isabs(config_arg):
        return Path(config_arg).resolve()

    name = config_arg or "config.ini"
    base = app_dir()
    primary = (base / name).resolve()
    if primary.exists():
        return primary

    # Source fallback: project root (parent of app/)
    if not getattr(sys, "frozen", False):
        root_candidate = (base.parent / name).resolve()
        if root_candidate.exists():
            return root_candidate

    return primary


def describe_config_binding(config_path: Path) -> str:
    """Short human-readable binding status for logs / UI."""
    exists = config_path.exists()
    return (
        f"config={'FOUND' if exists else 'MISSING'} | "
        f"path={config_path}"
    )
