"""R18: every Python dependency pinned with `==`, and every locked registry package carries a hash."""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXACT = re.compile(r"^[A-Za-z0-9_.\-\[\]]+==[0-9][A-Za-z0-9.+\-]*$")

with (ROOT / "pyproject.toml").open("rb") as fh:
    pyproject = tomllib.load(fh)

specs: list[str] = list(pyproject["project"].get("dependencies", []))
specs += pyproject["build-system"]["requires"]
for group in pyproject.get("dependency-groups", {}).values():
    specs += group

errors = [f"sin '==' exacto: {spec!r}" for spec in specs if not EXACT.match(spec.replace(" ", ""))]

lock_path = ROOT / "uv.lock"
if not lock_path.is_file():
    errors.append("falta uv.lock")
else:
    with lock_path.open("rb") as fh:
        lock = tomllib.load(fh)
    for package in lock.get("package", []):
        if "registry" not in package.get("source", {}):
            continue
        artifacts = package.get("wheels", []) + ([package["sdist"]] if "sdist" in package else [])
        if not artifacts or any("hash" not in artifact for artifact in artifacts):
            errors.append(f"uv.lock: {package['name']} sin hash en algún artefacto")

for error in errors:
    print(f"R18 FALLA · {error}", file=sys.stderr)
if not errors:
    print(f"R18 ok · {len(specs)} dependencias con '==' y uv.lock con hashes")
sys.exit(1 if errors else 0)
