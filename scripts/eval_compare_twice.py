"""`make eval-compare-twice`: G-DETERMINISM. Acceptance criterion nº 3 made a command.

Runs `evalgate eval compare` TWICE over each pair of reports of the fixture suite, in two separate processes
(a fresh interpreter each time: no shared state, another hash seed), and checks that both runs give the same
decision and the same sha256 of the report, leaving out only the fields of
`evals/report-hash-exclusions.yaml` (the timestamp and timings). Also checks each decision against
`expected.yaml`, written before the gate ever ran: identical and wrong would still be wrong.

Prints `G-DETERMINISM ratio=<identical pairs / pairs> n=<pairs>`; exit 1 unless every pair is identical and
as expected.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evalgate.gate.config import report_digest  # noqa: E402 - after the path line above

SUITE = ROOT / "evals" / "suites" / "compare-fixture"
EXIT_OF = {0: "pass", 1: "block"}


def once(head: str, out: Path) -> tuple[str, str]:
    """One run in its own process. Returns (decision by exit code, digest of the report)."""
    done = subprocess.run(
        [
            "evalgate",
            "eval",
            "compare",
            str(SUITE / "base.json"),
            str(SUITE / f"{head}.json"),
            "--gate",
            str(SUITE / "gate.yaml"),
            "--out",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode not in EXIT_OF:
        raise SystemExit(f"eval compare falló sobre {head} (exit {done.returncode}):\n{done.stderr}")
    exclusions = yaml.safe_load((ROOT / "evals" / "report-hash-exclusions.yaml").read_text("utf-8"))
    document = json.loads(out.read_text("utf-8"))
    if document["comparison"]["decision"] != EXIT_OF[done.returncode]:
        raise SystemExit(f"{head}: el código de salida y el informe no dicen lo mismo")
    return EXIT_OF[done.returncode], report_digest(document, [e["path"] for e in exclusions["exclusions"]])


def main() -> int:
    expected: dict[str, str] = yaml.safe_load((SUITE / "expected.yaml").read_text("utf-8"))
    identical, problems = 0, []
    with tempfile.TemporaryDirectory() as tmp:
        for head, wanted in sorted(expected.items()):
            first, second = once(head, Path(tmp) / f"{head}-1.json"), once(head, Path(tmp) / f"{head}-2.json")
            if first != second:
                problems.append(f"{head}: dos ejecuciones distintas: {first} y {second}")
                continue
            identical += 1
            if first[0] != wanted:
                problems.append(f"{head}: decidió {first[0]} y se esperaba {wanted}")
            print(f"{head:16} {first[0]:5}  sha256 {first[1][:16]}…  (dos ejecuciones idénticas)")
    total = len(expected)
    print(f"G-DETERMINISM ratio={identical / total:g} n={total}")
    for problem in problems:
        print(f"G-DETERMINISM FALLA · {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
