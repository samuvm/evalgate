#!/usr/bin/env bash
# Snapshot after a green `make done`: the reference the next test inventory is compared against.
# Copies src/, tests/ (WITHOUT tests/holdout: the held-out suite stays private), docs/, pyproject.toml,
# uv.lock and the test inventory, plus MANIFEST.sha256. Only scripts/done.py calls it.
set -euo pipefail
cd "$(dirname "$0")/.."

milestone="${1:?uso: save.sh <fase>}"
base=".snapshots/$(date +%Y-%m-%d)-fase${milestone}"
dest="$base"
i=2
while [ -e "$dest" ]; do dest="${base}-${i}"; i=$((i + 1)); done

mkdir -p "$dest"
rsync -a --exclude 'holdout/' --exclude '__pycache__/' src tests docs "$dest/"
cp pyproject.toml uv.lock "$dest/"
cp .gate/test-inventory.json "$dest/"
(cd "$dest" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 shasum -a 256 > MANIFEST.sha256)
echo "$dest"
