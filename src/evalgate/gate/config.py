"""The gate's configuration, built from docs/GOALS.yaml `comparacion` and a suite's metric rules.

R7: every parameter of the decision arrives from configuration. This module is where it arrives, and it
never repairs a configuration: a missing parameter, an unpaired bootstrap or a correction the gate does not
implement are refused with the name of the field, not replaced by something reasonable. A default is a
decision nobody approved.

Two parameters are not in GOALS.yaml today and come from the contract instead (retrieval-metrics.md §4): the
95 % of the interval and "more than three blocking metrics" for the correction. They are named constants
here, the only place they are written, and GOALS.yaml wins the day it declares them (`nivel_confianza`,
`correccion_desde`).
"""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from fractions import Fraction
from typing import Any

from evalgate.gate.compare import GateConfig, MetricRule
from evalgate.gate.decision import HOLM, Policy

CONTRACT_LEVEL = Fraction(95, 100)  # "IC 95 %", retrieval-metrics.md §4; the report field is literally `ci95`
CONTRACT_CORRECTION_ABOVE = 3  # "más de tres métricas bloqueantes", same section
MIN_REPLICATES = 1000  # docs/CONTRACTS/goals.schema.json: comparacion.n_resamples minimum
_RULE_KEYS = {"id", "blocking", "higher_is_better", "absolute"}
_SIMPLE_PATH = re.compile(r"^\$(\.\w+)+$")


class GateConfigError(ValueError):
    """The gate's configuration is not one the contract allows. Never repaired with a default."""


def _required(block: Mapping[str, Any], key: str) -> Any:
    if key not in block:
        raise GateConfigError(f"comparacion.{key} falta: la puerta no rellena parámetros por su cuenta")
    return block[key]


def _integer(value: Any, name: str, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise GateConfigError(f"{name} debe ser un entero >= {minimum}, no {value!r}")
    return value


def _rule(node: Mapping[str, Any]) -> MetricRule:
    if extra := sorted(node.keys() - _RULE_KEYS):
        raise GateConfigError(f"regla de métrica con campo no admitido: {', '.join(extra)}")
    if not isinstance(node.get("id"), str) or not node["id"]:
        raise GateConfigError(f"regla de métrica sin id: {dict(node)!r}")
    name = node["id"]
    if not isinstance(node.get("blocking"), bool):
        raise GateConfigError(f"{name}: blocking debe ser true o false, y es obligatorio")
    higher = node.get("higher_is_better", True)
    if not isinstance(higher, bool):
        raise GateConfigError(f"{name}: higher_is_better debe ser true o false")
    absolute = node.get("absolute")
    if absolute is not None and (isinstance(absolute, bool) or not isinstance(absolute, int | float)):
        raise GateConfigError(f"{name}: absolute debe ser un número, no {absolute!r}")
    return MetricRule(name, node["blocking"], higher, None if absolute is None else float(absolute))


def gate_config(comparacion: Mapping[str, Any], rules: Sequence[Mapping[str, Any]]) -> GateConfig:
    """Build the config or raise `GateConfigError` naming the field. Nothing is defaulted silently."""
    if _required(comparacion, "metodo") != "bootstrap":
        raise GateConfigError(f"comparacion.metodo debe ser bootstrap, no {comparacion['metodo']!r}")
    if _required(comparacion, "pareado") is not True:
        raise GateConfigError("comparacion.pareado debe ser true: no existe bootstrap no pareado (R8)")
    replicates = _integer(_required(comparacion, "n_resamples"), "comparacion.n_resamples", MIN_REPLICATES)
    seed = _integer(_required(comparacion, "semilla"), "comparacion.semilla", 0)
    correction = comparacion.get("correccion_multiple", HOLM)
    if correction not in {HOLM, None}:
        raise GateConfigError(
            f"comparacion.correccion_multiple {correction!r}: la puerta solo implementa {HOLM!r}"
        )

    level = CONTRACT_LEVEL
    if "nivel_confianza" in comparacion:
        raw = comparacion["nivel_confianza"]
        if isinstance(raw, bool) or not isinstance(raw, int | float) or not 0 < raw < 1:
            raise GateConfigError(f"comparacion.nivel_confianza debe estar entre 0 y 1 exclusive, no {raw!r}")
        level = Fraction(str(raw))
    above = CONTRACT_CORRECTION_ABOVE
    if "correccion_desde" in comparacion:
        above = _integer(comparacion["correccion_desde"], "comparacion.correccion_desde", 0)

    if not rules:
        raise GateConfigError("rules vacío: una puerta sin métricas que juzgar lo aprobaría todo")
    parsed = tuple(_rule(node) for node in rules)
    names = [rule.metric for rule in parsed]
    if repeated := sorted({name for name in names if names.count(name) > 1}):
        raise GateConfigError(f"métrica con dos reglas: {', '.join(repeated)}")
    return GateConfig(replicates, seed, Policy(level, correction, above), parsed)


def report_digest(document: Mapping[str, Any], excluded: Sequence[str]) -> str:
    """sha256 of a report without the fields of `evals/report-hash-exclusions.yaml` (G-DETERMINISM).

    Canonical JSON (sorted keys, fixed separators), so the digest depends on the content and not on how it
    was written. Exclusion paths are plain `$.a.b`; anything fancier is refused rather than half understood.
    The document is not modified.
    """
    kept = deepcopy(dict(document))
    for path in excluded:
        if not _SIMPLE_PATH.match(path):
            raise GateConfigError(f"exclusión {path!r}: solo se admiten rutas simples del tipo $.a.b")
        *parents, leaf = path.removeprefix("$.").split(".")
        node: Any = kept
        for key in parents:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict):
            node.pop(leaf, None)
    canonical = json.dumps(kept, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
