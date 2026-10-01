"""Hypothesis profiles per gate layer (CONSTITUCION §2.4): dev=25, gate=100, nightly=1000 examples.

And the single place where the measured goals are reported: the hook lives here, at the root of the test
tree, so it runs once however many suites the command selects.
"""

import os

import pytest
from _pytest.terminal import TerminalReporter
from hypothesis import settings

from tests._meter import METER, Meter

settings.register_profile("dev", max_examples=25)
settings.register_profile("gate", max_examples=100)
settings.register_profile("nightly", max_examples=1000)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(scope="session")
def meter() -> Meter:
    return METER


def pytest_terminal_summary(terminalreporter: TerminalReporter) -> None:
    for line in METER.lines():
        terminalreporter.write_line(line)
