"""The eval report of a run, in the shape of docs/CONTRACTS/eval-report.schema.json.

Pure: scores and facts in, a document out. Three things it guarantees beyond the schema:

- every prompt that took part is named with `{id, version, sha256}` and its role (R14): without that, a
  change in a metric cannot be traced to a change in a prompt;
- every metric points to its per-case values (`raw_path`), which is what `eval compare` pairs. A report
  without them could be read but not compared;
- `run_id` is a function of the inputs only (golden set, outputs of the system, judge prompt and sampling).
  The clock and the cache statistics are not inputs: a cold and a warm run of the same suite over the same
  outputs are the same run.

Digests are written `sha256:<hex>`: a bare hex string is what detect-secrets takes for a key.
"""

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from evalgate.evals.cache.store import CacheStats
from evalgate.evals.runner import Scores
from evalgate.evals.suite import Suite


def raw_rows(scores: Scores) -> dict[str, list[dict[str, Any]]]:
    """Per metric, the `{case_id, value}` rows `eval compare` reads, in case order."""
    return {
        metric: [{"case_id": case, "value": values[case]} for case in sorted(values)]
        for metric, values in scores.items()
    }


def eval_report(suite: Suite, scores: Scores, cache: CacheStats, facts: Mapping[str, Any]) -> dict[str, Any]:
    """The report document. `facts` carries what only the caller knows: digests, counts, machine, clock."""
    for metric, values in scores.items():
        if not values:
            raise ValueError(f"metric {metric} has no cases: an empty metric is not reported as a number")
    prompt = suite.judge_prompt
    prompt_digest = f"sha256:{prompt.sha256}"
    identity = json.dumps(
        [
            suite.name,
            facts["golden_sha256"],
            facts["sut_outputs_sha256"],
            suite.generator_model,
            [suite.judge_id, prompt.id, prompt.version, prompt_digest, dict(sorted(suite.judge_sampling.items()))],
        ],
        sort_keys=True,
    )
    environment: dict[str, Any] = {
        "hardware": facts["hardware"],
        "python": facts["python"],
        "deterministic": facts["deterministic"],
        "models": {"generator": suite.generator_model, "judge": prompt.model},
    }
    if isinstance(suite.judge_sampling.get("seed"), int):
        environment["seed"] = suite.judge_sampling["seed"]
    saved_or_spent = cache.spent_tokens + cache.saved_tokens
    return {
        "contract_version": 1,
        "run_id": f"{suite.name}-{hashlib.sha256(identity.encode()).hexdigest()[:16]}",
        "project": "evalgate",
        "suite": suite.name,
        "created_at": facts["created_at"],
        "environment": environment,
        "dataset": {
            "name": suite.golden_dir.rstrip("/").rsplit("/", maxsplit=1)[-1],
            "version": 1,
            "n_cases": facts["n_cases"],
            "n_negative_cases": facts["n_negative_cases"],
            "sha256": facts["golden_sha256"],
        },
        "prompts": [{"id": prompt.id, "version": prompt.version, "sha256": prompt_digest, "role": "judge"}],
        "metrics": [
            {
                "id": metric,
                "value": math.fsum(values.values()) / len(values),
                "n": len(values),
                "unit": "ratio",
                "raw_path": f"{facts['raw_dir']}/{metric}.json",
            }
            for metric, values in scores.items()
        ],
        "cache": {
            "judge_hits": cache.hits,
            "judge_misses": cache.misses,
            "savings_ratio": cache.saved_tokens / saved_or_spent if saved_or_spent else 0.0,
        },
    }
