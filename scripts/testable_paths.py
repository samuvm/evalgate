"""Print the [tool.gate].testable paths that exist today, for mypy. Paths not built yet are skipped."""

from gatelib import ROOT, tool_gate

print(" ".join(p for p in tool_gate()["testable"] if (ROOT / p).exists()))
