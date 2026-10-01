"""R17: every number in README.md comes from evals/reports/. Thin wrapper over `scripts/report.py --check`."""

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.exit(subprocess.run([sys.executable, str(SCRIPTS / "report.py"), "--check"], check=False).returncode)
