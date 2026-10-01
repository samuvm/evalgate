"""What a goal measured, kept across tests and written once at the end of the run.

A meta medida con Hypothesis produce un número por ejemplo, y lo que el informe necesita es el agregado.
Cada test acumula aquí y `tests/conftest.py` escribe una línea `G-XXX key=value` por meta a través del
terminal reporter, que sobrevive a `pytest -q` sin `-s`: así es como `docs/GOALS.yaml` declara los comandos,
y un `print` dentro de un test que pasa no se ve.
"""


class Meter:
    def __init__(self) -> None:
        self.checks: dict[str, list[int]] = {}
        self.worst: dict[str, dict[str, float]] = {}

    def check(self, goal: str, ok: bool) -> None:
        """One more case for `goal`, and whether it held. The ratio of these is what the goal publishes."""
        hits = self.checks.setdefault(goal, [0, 0])
        hits[0] += int(ok)
        hits[1] += 1

    def observe(self, goal: str, key: str, value: float) -> None:
        """Keep the worst value seen: a maximum that only holds on average is not a maximum."""
        seen = self.worst.setdefault(goal, {})
        seen[key] = max(seen.get(key, 0.0), value)

    def lines(self) -> list[str]:
        reported: list[str] = []
        for goal in sorted(set(self.checks) | set(self.worst)):
            parts = [f"{key}={value:g}" for key, value in sorted(self.worst.get(goal, {}).items())]
            if goal in self.checks:
                ok, total = self.checks[goal]
                parts = [f"ratio={ok / total if total else 0:g}", f"n={total}", *parts]
            reported.append(f"{goal} " + " ".join(parts))
        return reported


METER = Meter()
