"""`evalgate eval self-gate`: the repository behind its own gate (RULES R16, ROADMAP F9). I/O and wiring only.

For each suite, the PUBLISHED report (`evals/reports/<suite>.json`, the numbers the README shows) is the
baseline and the report the code of today gives from the recorded outputs is HEAD. A change to a metric, to
the recorded answers or to the verdicts that lowers a blocking metric beyond what the gate tolerates is
blocked, exactly as it would be in somebody else's repository. No model is called.
"""

import tempfile
from pathlib import Path

from evalgate.cli import compare as compare_cli
from evalgate.cli import eval_run
from evalgate.gate.compare import Comparison

SUITES = ("rag-app", "rag-app-v2")
NO_MODEL = "http://self-gate.invalid/v1"  # never dialled: a recorded run does not call a model


def check(root: Path, suite: str) -> Comparison:
    """Recompute `suite` from its recorded cache and judge it against the published report."""
    suite_dir = root / "evals" / "suites" / suite
    with tempfile.TemporaryDirectory() as scratch:
        eval_run.run(suite_dir, root, Path(scratch), refresh=False, base_url=NO_MODEL)
        return compare_cli.run(
            root / "evals" / "reports" / f"{suite}.json",
            Path(scratch) / f"{suite}.json",
            suite_dir / "gate.yaml",
            root / "docs" / "GOALS.yaml",
            Path(scratch) / "comparison.json",
        )
