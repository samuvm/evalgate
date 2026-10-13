"""The published meta-evaluation, measured again from the published matrices. Slow on purpose: every
decision of every run is bootstrapped again (about 80 s), so it lives outside `make test-fast` and runs in
`make test` and in `make done`. `evalgate meta report --check` does the same for the official document.
"""

import json
from pathlib import Path

import pytest

from evalgate.cli import meta

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("document", "source", "n_cases"),
    [("meta-eval.json", "fp-matrix.parquet", 200), ("meta-eval-60.json", "fp-matrix-60.parquet", 60)],
)
def test_the_published_numbers_are_what_the_published_matrix_gives(
    tmp_path: Path, document: str, source: str, n_cases: int
) -> None:
    """Nobody typed them: each matrix in the repository gives its three blocks again, to the last digit.
    Both measurements are published: the one over the 200 cases and the earlier one over 60."""
    published = json.loads((ROOT / "evals" / "reports" / document).read_text("utf-8"))
    path, goals, out = Path("evals/reports") / source, ROOT / "docs" / "GOALS.yaml", tmp_path / "m.json"

    meta.fp(path, ROOT, goals, out)
    meta.mde(path, ROOT, goals, out)
    again = meta.sensitivity(path, ROOT, goals, out)

    for block in (
        "fp_rate_baseline_fixed",
        "mde_pp",
        "power",
        "n_decisiones",
        "n_casos_subsuite",
        "fuente_de_ruido",
    ):
        assert again[block] == published[block], block
    assert published["n_decisiones"] >= 49, "G-GATE-FP asks for at least 49 decisions"
    assert published["n_casos_subsuite"] == n_cases
