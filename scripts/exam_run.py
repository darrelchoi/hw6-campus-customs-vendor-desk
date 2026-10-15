"""Problem 8: run the final defended agent (all three layers) on the 10 exam documents.

    python scripts/exam_run.py

Writes output/exam_results.json, one entry per exam file, straight from the agent's output and the
API's token counts. Nothing is edited by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import run  # noqa: E402
from models import DEFENSE_LAYERS  # noqa: E402
from tools import TRAP_LOG  # noqa: E402

DOCS = sorted((ROOT / "data" / "exam_docs").iterdir())
OUT = ROOT / "output" / "exam_results.json"


def main() -> None:
    results = []
    for doc in DOCS:
        output, usage = run(doc, "with_cache", DEFENSE_LAYERS)
        traps = [c for c in json.loads(TRAP_LOG.read_text()) if c["run_id"] == usage["run_id"]]
        results.append({
            "file": doc.name,
            **output.model_dump(),
            "trap_tool_called": bool(traps),
            "input_tokens": usage["input_tokens"],
            "cached_tokens": usage["cache_read_tokens"],
            "output_tokens": usage["output_tokens"],
            "cost_usd": usage["cost_usd"]["total"],
        })
        OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    print(f"\n{len(results)} exam documents | trap calls: {sum(r['trap_tool_called'] for r in results)} | "
          f"total ${sum(r['cost_usd'] for r in results):.6f}")


if __name__ == "__main__":
    main()
