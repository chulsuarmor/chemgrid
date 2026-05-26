"""Canonical ChemGrid resource path resolver.

Resource lookup must work in development, PyInstaller one-file extraction,
one-dir executable layouts, and portable ZIP layouts with exe-adjacent
``_internal`` directories.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable


_RESOURCE_ENV_VAR = "CHEMGRID_RESOURCE_ROOT"


def _module_dir() -> Path:
    return Path(__file__).resolve().parent


def _dev_src_app_dir(module_dir: Path) -> Path | None:
    if module_dir.name == "app" and module_dir.parent.name == "src":
        return module_dir
    if module_dir.name == "_source":
        candidate = module_dir.parent / "src" / "app"
        return candidate
    return None


def resource_roots() -> list[Path]:
    """Return candidate resource roots in canonical search order."""
    roots: list[Path] = []

    env_root = os.environ.get(_RESOURCE_ENV_VAR)
    if env_root:
        roots.append(Path(env_root))

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        meipass_root = Path(str(meipass))
        roots.append(meipass_root)
        roots.append(meipass_root / "_internal")

    exe_path = Path(sys.executable).resolve()
    exe_dir = exe_path.parent
    roots.append(exe_dir)
    roots.append(exe_dir / "_internal")

    module_dir = _module_dir()
    dev_src_app = _dev_src_app_dir(module_dir)
    if dev_src_app is not None:
        roots.append(dev_src_app)
    roots.append(module_dir)

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        text = str(root.resolve() if root.exists() else root.absolute()).lower()
        if text not in seen:
            deduped.append(root)
            seen.add(text)
    return deduped


def resource_candidates(name: str | os.PathLike[str]) -> list[Path]:
    """Return all candidate locations for a resource name."""
    rel = Path(name)
    if rel.is_absolute():
        return [rel]
    return [root / rel for root in resource_roots()]


def resource_path(name: str | os.PathLike[str]) -> Path:
    """Return the first existing resource path, or the first candidate."""
    candidates = resource_candidates(name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def existing_resource_path(name: str | os.PathLike[str]) -> Path | None:
    """Return the first existing resource path, or None."""
    for candidate in resource_candidates(name):
        if candidate.exists():
            return candidate
    return None


def required_resources_exist(names: Iterable[str]) -> dict[str, str]:
    """Map resource names to resolved existing paths, raising on omissions."""
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for name in names:
        path = existing_resource_path(name)
        if path is None:
            missing.append(name)
        else:
            resolved[name] = str(path)
    if missing:
        raise FileNotFoundError("Missing ChemGrid resources: " + ", ".join(missing))
    return resolved
