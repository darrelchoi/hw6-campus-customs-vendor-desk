"""Problem 4: run all 12 practice documents with and without prompt caching.

    python scripts/cache_test.py

Every model call from both setups goes to output/cache_test.json, with the token counts the API
reported and the dollar cost from data/prices.json. The script then checks the API's numbers prove
each setup did what it claims: without_cache must show 0 cached tokens on every call.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import run  # noqa: E402

DOCS = sorted((ROOT / "data" / "practice_docs").iterdir())
KEY = {row["file"]: row for row in json.loads((ROOT / "data" / "practice_key.json").read_text())}
OUT = ROOT / "output" / "cache_test.json"
FIELDS = ("vendor", "sku", "unit_price", "lead_time_days", "min_order", "decision")


def main() -> None:
    calls, runs = [], []
    # without_cache first, so the with_cache setup starts from its own first cache write.
    for setup in ("without_cache", "with_cache"):
        for doc in DOCS:
            output, usage = run(doc, setup)
            wrong = [f for f in FIELDS if getattr(output, f) != KEY[doc.name][f]]
            runs.append({"setup": setup, "document": doc.name, "run_id": usage["run_id"], "wrong_fields": wrong})
            for i, req in enumerate(usage["per_request"], 1):
                calls.append({
                    "setup": setup,
                    "document": doc.name,
                    "run_id": usage["run_id"],
                    "call": i,
                    "time": usage["time"],
                    **req,
                    "uncached_input_tokens": req["input_tokens"] - req["cache_read_tokens"] - req["cache_write_tokens"],
                })
            OUT.write_text(json.dumps({"calls": calls, "runs": runs}, indent=2))

    # Proof checks from the API's own numbers.
    for setup in ("without_cache", "with_cache"):
        mine = [c for c in calls if c["setup"] == setup]
        read = sum(c["cache_read_tokens"] for c in mine)
        hits = sum(c["cache_read_tokens"] > 0 for c in mine)
        cost = sum(c["cost_usd"]["total"] for c in mine)
        print(f"{setup:14} calls={len(mine)} calls_with_cache_hits={hits} cache_read_tokens={read:,} cost=${cost:.6f}")
    leaked = [c for c in calls if c["setup"] == "without_cache" and c["cache_read_tokens"]]
    print("without_cache proof:", "FAILED, cached tokens found" if leaked else "OK, 0 cached tokens on every call")


if __name__ == "__main__":
    main()
