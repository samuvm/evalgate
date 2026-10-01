"""`make done MILESTONE=N` and `make gate-full`: the Definition of Done of CONSTITUCION §5.

Checks run in order and stop at the first failure. Which goals block comes from docs/GOALS.yaml
(`bloqueante_desde_fase`), never from this file: steps 4-7 read their command and threshold from there.
Writes .claude/state/gate-status.json and the gate-only fields of STATE.md; on a green `done` it also writes
.claude/state/test-inventory.json and takes a snapshot with scripts/save.sh.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gatelib import ROOT, compare, goal, goals, is_blocking

STATE_DIR = ROOT / ".claude" / "state"
STATUS = STATE_DIR / "gate-status.json"
INVENTORY = STATE_DIR / "test-inventory.json"
STATE = STATE_DIR / "STATE.md"
SUITE_DIRS = "tests/unit tests/property tests/contract tests/integration tests/adversarial"
HANDLED_GOALS = {"G-FUNC-COV", "G-LINE-COV", "G-MUTATION"}  # steps 4-6; step 7 evaluates the rest
# Regenerable or third-party directories. The same regex generated .secrets.baseline.
# test-inventory.json is excluded for the same reason as .secrets.baseline: the gate itself rewrites it
# (step 9) with the sha256 of every test file, and every legitimate change to a test produces a new digest
# that the entropy detector reports as a secret. It is an index of digests, never a place a secret can be
# written to by hand. Excluding it does not weaken step 12: the files it indexes are all scanned.
SECRETS_EXCLUDED = (
    r"(\.venv|\.snapshots|mutants|\.mypy_cache|\.pytest_cache|\.ruff_cache)/"
    r"|\.secrets\.baseline$|\.claude/state/test-inventory\.json$"
)


@dataclass
class Step:
    name: str
    ok: bool
    detail: str
    blocking: bool = True
    numbers: dict[str, Any] = field(default_factory=dict)


def sh(command: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    result = subprocess.run(  # noqa: S602 - commands come from the Makefile and GOALS.yaml, not from input
        command,
        shell=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        check=False,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def tail(text: str, lines: int = 15) -> str:
    return "\n".join(text.splitlines()[-lines:])


def static() -> Step:
    testable = sh("python scripts/testable_paths.py")[1]
    commands = [
        "ruff check .",
        "ruff format --check .",
        f"mypy {testable}",
        "bandit -q -r src",
        "python scripts/check_gate_config.py",
        "python scripts/rules/self_gate.py",
        "python scripts/rules/pins.py",
        "python scripts/rules/example_is_client.py",
        "python scripts/rules/readme_numbers.py",
        "python scripts/rules/finally_on_generators.py",  # R2 en el módulo, desde F2
        "python scripts/rules/stream_closed_in_request.py",  # R2 en el montaje (qa H-13), desde F2
        "python scripts/rules/no_genai_literals.py",  # R5, desde F3
        "python scripts/rules/no_blocking_export.py",  # R1, desde F3
        "python scripts/gen_semconv.py --check",  # semconv generado, no escrito (mapa), desde F3
        "python scripts/rules/sse_corpus_coverage.py",  # RULES §4.2 punto 3, desde F2
    ]
    for command in commands:
        code, out = sh(command)
        if code != 0:
            return Step("1 · estáticos y reglas", False, f"$ {command}\n{tail(out)}")
    return Step("1 · estáticos y reglas", True, f"{len(commands)} comprobaciones")


def suite(profile: str) -> Step:
    code, out = sh(f"pytest {SUITE_DIRS} -q -p no:cacheprovider", {"HYPOTHESIS_PROFILE": profile})
    summary = out.splitlines()[-1] if out else ""
    return Step("2 · suite completa", code == 0, f"perfil Hypothesis {profile} · {summary}")


def holdout(milestone: int) -> Step:
    if not (ROOT / "tests" / "holdout").is_dir():
        if milestone == 0:
            return Step(
                "3 · reserva", True, "no existe aún: se instala al cerrar F1 (CONSTITUCION §9 paso 7)", False
            )
        return Step("3 · reserva", False, "falta tests/holdout/: CONSTITUCION §9 paso 7 (D-09)")
    code, out = sh("pytest tests/holdout -q -p no:cacheprovider")
    return Step("3 · reserva", code == 0, out.splitlines()[-1] if out else "")


def function_coverage(milestone: int) -> Step:
    meta = goal("G-FUNC-COV")
    code, out = sh(meta["comando"])
    missing = re.search(r"funciones_sin_test=(\d+)", out)
    value = int(missing[1]) if missing else None
    ok = (
        code == 0
        and value is not None
        and compare(value, meta["umbral"]["operador"], meta["umbral"]["valor"])
    )
    detail = f"funciones públicas sin test = {value}" + ("" if ok else f"\n{tail(out)}")
    return Step("4 · cobertura por función", ok, detail, is_blocking(meta, milestone), {"G-FUNC-COV": value})


def json_path(document: Any, path: str) -> Any:
    """Minimal `$.a.b` JSONPath: the only form GOALS.yaml uses outside filter expressions."""
    value = document
    for key in path.removeprefix("$.").split("."):
        value = value[key]
    return value


def artefact_value(artefacto: str) -> Any:
    """Value at `file#$.path`. `<fecha>`-style placeholders match the newest file; paths may be absolute."""
    file_part, _, path = artefacto.partition("#")
    pattern = re.sub(r"<[^>]+>", "*", file_part)
    candidates = [Path(p) for p in glob.glob(str(ROOT / pattern))]  # ROOT / absolute == absolute
    if not candidates:
        raise FileNotFoundError(f"artefacto inexistente: {file_part}")
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    return json_path(json.loads(newest.read_text(encoding="utf-8")), path)


def line_coverage(milestone: int) -> Step:
    meta = goal("G-LINE-COV")
    code, out = sh(meta["comando"])
    if code != 0:
        return Step("5 · cobertura de línea", False, tail(out), is_blocking(meta, milestone))
    value = round(float(artefact_value(meta["artefacto"])), 2)
    ok = compare(value, meta["umbral"]["operador"], meta["umbral"]["valor"])
    detail = f"{value} % (umbral {meta['umbral']['operador']} {meta['umbral']['valor']})"
    return Step("5 · cobertura de línea", ok, detail, is_blocking(meta, milestone), {"G-LINE-COV": value})


def mutation(milestone: int) -> Step:
    meta = goal("G-MUTATION")
    if not is_blocking(meta, milestone):
        return Step("6 · mutación", True, f"no activa hasta F{meta['bloqueante_desde_fase']}", False)
    code, out = sh(meta["comando"])
    if code != 0:
        return Step("6 · mutación", False, f"$ {meta['comando']}\n{tail(out)}")
    value = float(artefact_value(meta["artefacto"]))
    ok = compare(value, meta["umbral"]["operador"], meta["umbral"]["valor"])
    return Step("6 · mutación", ok, f"{value} % muertos", True, {"G-MUTATION": value})


def reported_number(goal_id: str, out: str, code: int) -> Any:
    """What a pass/fail goal measured: `G-XXX key=value` lines if the test prints them, else pytest totals."""
    lines = [line for line in out.splitlines() if line.startswith(f"{goal_id} ")]
    declared = [kv for line in lines for kv in re.findall(r"(\w+)=(\d+(?:\.\d+)?)", line)]
    if declared:
        return {key: float(v) if "." in v else int(v) for key, v in declared}
    passed = sum(int(n) for n in re.findall(r"(\d+) passed", out))
    failed = sum(int(n) for n in re.findall(r"(\d+) failed", out))
    if passed + failed:
        return {"ratio": round(passed / (passed + failed), 4), "n": passed + failed}
    return "pasa" if code == 0 else "falla"


def active_goals(milestone: int) -> Step:
    active = [m for m in goals()["metas"] if is_blocking(m, milestone) and m["id"] not in HANDLED_GOALS]
    numbers: dict[str, Any] = {}
    for meta in active:
        code, out = sh(meta["comando"])
        if meta["artefacto"] == ".claude/state/gate-status.json":
            ok, numbers[meta["id"]] = code == 0, reported_number(meta["id"], out, code)
        elif "#" in meta["artefacto"] and code == 0:
            value = artefact_value(meta["artefacto"])
            ok, numbers[meta["id"]] = (
                compare(value, meta["umbral"]["operador"], meta["umbral"]["valor"]),
                value,
            )
        else:
            ok = False
        if not ok:
            return Step(
                "7 · metas activas",
                False,
                f"{meta['id']} no pasa\n$ {meta['comando']}\n{tail(out)}",
                True,
                numbers,
            )
    return Step("7 · metas activas", True, f"{len(active)} metas activas en F{milestone}", True, numbers)


def thresholds_lock() -> Step:
    lock = ROOT / "thresholds.lock"
    digest = hashlib.sha256((ROOT / "docs" / "GOALS.yaml").read_bytes()).hexdigest()
    if not lock.is_file():
        return Step(
            "8 · umbrales intactos", False, "falta thresholds.lock: solo Samuel lo genera (CONSTITUCION §3)"
        )
    pinned = lock.read_text(encoding="utf-8").split()[0]
    return Step(
        "8 · umbrales intactos", pinned == digest, f"sha256(GOALS.yaml)={digest[:12]}… lock={pinned[:12]}…"
    )


def last_snapshot() -> Path | None:
    snapshots = sorted((ROOT / ".snapshots").glob("*/test-inventory.json"))
    return snapshots[-1] if snapshots else None


def inventory() -> Step:
    reference = last_snapshot()
    command = "python scripts/test_inventory.py" + (
        f" --against {reference}" if reference else " --against /nonexistent"
    )
    code, out = sh(command)
    return Step("9 · inventario de tests", code == 0, tail(out, 5))


def debt() -> Step:
    code, out = sh("python scripts/debt.py")
    return Step("10 · deuda bajo tope", code == 0, tail(out, 5))


def documentation(milestone: int) -> Step:
    changelog = re.sub(r"<!--.*?-->", "", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), flags=re.S)
    if not re.search(rf"^## \[[^\]]+\] · F{milestone} ·", changelog, re.M):
        return Step("11 · documentación", False, f"CHANGELOG.md sin entrada '## [x.y.z] · F{milestone} · …'")
    journal = (ROOT / "docs" / "JOURNAL.md").read_text(encoding="utf-8").split("\n## ")
    sources = [changelog, *(s for s in journal if "ENTRADA DE EJEMPLO" not in s.splitlines()[0])]
    sources += [p.read_text(encoding="utf-8") for p in (ROOT / "docs" / "adr").glob("[0-9]*.md")]
    referenced = {n for text in sources for n in re.findall(r"ADR-(\d{3})", text)}
    missing = sorted(
        n for n in referenced if n != "000" and not list((ROOT / "docs" / "adr").glob(f"{n}-*.md"))
    )
    ok = not missing
    return Step(
        "11 · documentación", ok, "ADR referenciados sin fichero: " + ", ".join(missing) if missing else "ok"
    )


def secrets() -> Step:
    code, out = sh(f"detect-secrets scan --all-files --exclude-files '{SECRETS_EXCLUDED}'")
    if code != 0:
        return Step("12 · sin secretos", False, tail(out))
    found = json.loads(out)["results"]
    baseline = json.loads((ROOT / ".secrets.baseline").read_text(encoding="utf-8"))["results"]
    known = {(f, s["hashed_secret"]) for f, items in baseline.items() for s in items}
    new = sorted(
        {
            f"{f}:{s['line_number']}"
            for f, items in found.items()
            for s in items
            if (f, s["hashed_secret"]) not in known
        }
    )
    return Step(
        "12 · sin secretos", not new, "hallazgos nuevos: " + ", ".join(new) if new else "0 hallazgos nuevos"
    )


def write_state(fields: dict[str, str]) -> None:
    text = STATE.read_text(encoding="utf-8")
    for key, value in fields.items():
        text = re.sub(rf"^{key}:.*$", f"{key}: {value}", text, count=1, flags=re.M)
    STATE.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--milestone", type=int, required=True)
    parser.add_argument("--mode", choices=["done", "full"], default="done")
    args = parser.parse_args()
    n = args.milestone

    plan: list[Callable[[], Step]]
    if args.mode == "full":
        plan = [static, lambda: suite("gate"), lambda: active_goals(n), thresholds_lock, secrets]
    else:
        plan = [
            static,
            lambda: suite("nightly"),
            lambda: holdout(n),
            lambda: function_coverage(n),
            lambda: line_coverage(n),
            lambda: mutation(n),
            lambda: active_goals(n),
            thresholds_lock,
            inventory,
            debt,
            lambda: documentation(n),
            secrets,
        ]

    steps: list[Step] = []
    for check in plan:
        step = check()
        steps.append(step)
        mark = "ok " if step.ok else ("ROJO" if step.blocking else "info")
        print(f"[{mark}] {step.name} · {step.detail.splitlines()[0] if step.detail else ''}")
        if not step.ok and step.blocking:
            print(step.detail, file=sys.stderr)
            break

    green = all(s.ok or not s.blocking for s in steps) and len(steps) == len(plan)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    STATUS.write_text(
        json.dumps(
            {
                "mode": args.mode,
                "milestone": n,
                "green": green,
                "at": now,
                "steps": [asdict(s) for s in steps],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    label = "done" if args.mode == "done" else "gate-full"
    fields = {"ultimo_gate": f'"{label} F{n} {"verde" if green else "rojo"} {now}"'}
    if green:
        fields["ultima_verificacion"] = now
    if green and args.mode == "done":
        INVENTORY.write_text(sh("python scripts/test_inventory.py")[1] + "\n", encoding="utf-8")
        code, out = sh(f"bash scripts/save.sh {n}")
        if code != 0:
            print(out, file=sys.stderr)
            return 1
        snapshot = out.splitlines()[-1]
        fields |= {"gate_verde_en": now, "snapshot_ultimo_verde": snapshot}
        measured = {k: v for s in steps for k, v in s.numbers.items() if v is not None}
        report = {
            "milestone": n,
            "at": now,
            "numbers": measured,
            "snapshot": snapshot,
            "source": str(STATUS.relative_to(ROOT)),
        }
        (ROOT / "evals" / "reports" / f"gate-F{n}.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        sh("python scripts/report.py")  # R17: README numbers regenerated from evals/reports/
    write_state(fields)
    print(f"{label} F{n}: {'VERDE' if green else 'ROJO'}")
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
