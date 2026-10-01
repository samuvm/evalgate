"""Shared readers for the gate scripts: [tool.gate], GOALS.yaml and STATE.md. Standard library + PyYAML."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def tool_gate() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        gate: dict[str, Any] = tomllib.load(fh)["tool"]["gate"]
    return gate


def goals() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / "docs/GOALS.yaml").read_text(encoding="utf-8"))
    return data


def goal(goal_id: str) -> dict[str, Any]:
    for meta in goals()["metas"]:
        if meta["id"] == goal_id:
            found: dict[str, Any] = meta
            return found
    raise KeyError(f"goal {goal_id} not found in docs/GOALS.yaml")


def is_blocking(meta: dict[str, Any], milestone: int) -> bool:
    since = meta["bloqueante_desde_fase"]
    return since is not None and since <= milestone


def active_phase() -> int:
    match = re.search(
        r"^fase_activa:\s*(\d+)", (ROOT / ".claude/state/STATE.md").read_text(encoding="utf-8"), re.M
    )
    if match is None:
        raise ValueError("fase_activa not found in .claude/state/STATE.md")
    return int(match[1])


def python_files(paths: list[str]) -> list[Path]:
    """Existing .py files under the given [tool.gate] paths (packages or single files)."""
    files: list[Path] = []
    for entry in paths:
        path = ROOT / entry
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return files


def compare(value: float, operator: str, threshold: float) -> bool:
    ops = {
        ">=": value >= threshold,
        ">": value > threshold,
        "<=": value <= threshold,
        "<": value < threshold,
        "==": value == threshold,
        "!=": value != threshold,
    }
    return ops[operator]
