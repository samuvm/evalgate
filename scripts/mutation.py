"""G-MUTATION (`make mutation`, PARA-SAMUEL P-003): mutmut 3.x on [tool.mutmut].only_mutate.

mutmut 3.7.0 always copies the whole `tests/` directory into `mutants/` (`also_copy` is hard-coded), so
running it at the project root would leave tests/holdout/ readable under mutants/tests/holdout/, a path
the builder's `deny` does not cover. So it runs in a throwaway copy of the project that never contains the
holdout, with this project's interpreter. Only the suites in [tool.mutmut].pytest_add_cli_args_test_selection
kill mutants; the holdout never takes part in a builder measure.

killed_pct = 100 * killed / (total - skipped). Survived, no_tests, timeout and suspicious count against it:
a mutant no test notices is not killed.

Usage: python scripts/mutation.py [--milestone N]   (default: fase_activa of STATE.md)
Writes evals/reports/mutation-F<N>.json and prints `G-MUTATION killed_pct=...`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from gatelib import ROOT, active_phase

NOT_COPIED = {
    ".venv",
    "mutants",
    ".snapshots",
    ".run",
    ".claude",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".hypothesis",
    "__pycache__",
    ".coverage",
}


def ignore(directory: str, names: list[str]) -> set[str]:
    skipped = NOT_COPIED.intersection(names)
    if Path(directory).resolve() == ROOT / "tests":
        skipped.add("holdout")
    return skipped


def mutmut(workdir: Path, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "mutmut", *args],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
        raise SystemExit(f"mutmut {' '.join(args)} falló (exit {result.returncode}):\n{tail}")
    return result.stdout


def not_killed(workdir: Path) -> list[dict[str, str]]:
    """Each mutant that survived (or timed out, or had no test) with its diff: what a new test must kill."""
    found = []
    for line in mutmut(workdir, "results").splitlines():
        name, sep, status = line.strip().rpartition(": ")
        if sep:
            found.append({"mutant": name, "status": status, "diff": mutmut(workdir, "show", name).strip()})
    return found


def measure(workdir: Path) -> dict[str, Any]:
    mutmut(workdir, "run")
    mutmut(workdir, "export-cicd-stats")
    stats: dict[str, Any] = json.loads((workdir / "mutants" / "mutmut-cicd-stats.json").read_text("utf-8"))
    if stats["check_was_interrupted_by_user"]:
        raise SystemExit("mutmut interrumpido: la medida no está completa")
    judged = stats["total"] - stats["skipped"]
    if judged <= 0:
        raise SystemExit("mutmut no generó ningún mutante: no hay nada que medir")
    killed_pct = round(100 * stats["killed"] / judged, 2)
    return {**stats, "killed_pct": killed_pct, "not_killed": not_killed(workdir)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--milestone", type=int, default=None)
    milestone = parser.parse_args().milestone
    phase = active_phase() if milestone is None else milestone

    with tempfile.TemporaryDirectory(prefix="evalgate-mutation-") as tmp:
        workdir = Path(tmp) / "project"
        shutil.copytree(ROOT, workdir, ignore=ignore, symlinks=True)
        if (workdir / "tests" / "holdout").exists():  # the whole point of the copy
            raise SystemExit("la copia contiene tests/holdout/: abortado")
        stats = measure(workdir)

    with (ROOT / "pyproject.toml").open("rb") as fh:
        config = tomllib.load(fh)["tool"]["mutmut"]
    report = {
        "milestone": phase,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "tool": f"mutmut=={version('mutmut')}",
        "only_mutate": config["only_mutate"],
        "killing_suites": config["pytest_add_cli_args_test_selection"],
        **stats,
    }
    out = ROOT / "evals" / "reports" / f"mutation-F{phase}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"G-MUTATION killed_pct={stats['killed_pct']} killed={stats['killed']} "
        f"survived={stats['survived']} no_tests={stats['no_tests']} total={stats['total']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
