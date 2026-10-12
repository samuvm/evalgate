"""Hypothesis profiles per gate layer: dev=25, gate=100, nightly=1000 examples.

And the single place where the measured goals are reported: the hook lives here, at the root of the test
tree, so it runs once however many suites the command selects.
"""

import os

import pytest
from _pytest.terminal import TerminalReporter
from hypothesis import settings

from tests._meter import METER, Meter

# No per-example deadline: Hypothesis's default 200 ms is a wall-clock assertion, and on a shared machine it
# fails correct code (2026-10-12: three properties that take 2 ms took 250-420 ms with the load at 15-19).
# Speed is guarded where it belongs, by the budget of `make test-fast`, not example by example.
settings.register_profile("dev", max_examples=25, deadline=None)
settings.register_profile("gate", max_examples=100, deadline=None)
settings.register_profile("nightly", max_examples=1000, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(scope="session")
def meter() -> Meter:
    return METER


def pytest_terminal_summary(terminalreporter: TerminalReporter) -> None:
    for line in METER.lines():
        terminalreporter.write_line(line)
