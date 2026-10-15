"""Campus Customs vendor desk agent: entry point.

    python agent.py --doc data/practice_docs/p01_bluehen_quote.html                 # all defenses (default)
    python agent.py --doc data/practice_docs/p01_bluehen_quote.html --no-defenses   # Problem 3 agent
    python agent.py --doc ... --defenses code,prompt                                 # any subset of layers

Reads one vendor document, extracts vendor / SKU / price / lead time / minimum order, and recommends
(or not) following the Shop Handbook. Every run appends to output/usage_log.json and output/audit_trail.json.

Defense layers (Problem 6), each switchable:
- code:   tools.read_document passes the model only the text a person would see, fenced as untrusted.
- design: Python, not the model, applies the four purchasing checks and writes the reason; numbers must
          appear in the document; send_email / approve_payment sit behind a human sign-off gate.
- prompt: prompts/prompt.md security rules (prompts/prompt_no_defenses.md is the Problem 3 prompt).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # quiet startup banner

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, UsageLimits
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from models import (
    DATA_DIR,
    DEFENSE_LAYERS,
    MAX_REQUESTS_PER_RUN,
    MODEL_NAME,
    OUTPUT_DIR,
    ROOT,
    AgentDeps,
    VendorDecision,
)
from tools import TOOLS, TRAP_LOG, append_json

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")  # PORTKEY_API_KEY lives in the course-root .env

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
PROMPT_FILE = ROOT / "prompts" / "prompt.md"  # with the prompt-layer security rules
PROMPT_NO_DEFENSES_FILE = ROOT / "prompts" / "prompt_no_defenses.md"  # the Problem 3 prompt
HANDBOOK_FILE = DATA_DIR / "shop_handbook.md"
PRICES = json.loads((DATA_DIR / "prices.json").read_text())[MODEL_NAME]
USAGE_LOG = OUTPUT_DIR / "usage_log.json"
AUDIT_LOG = OUTPUT_DIR / "audit_trail.json"

# Prompt-cache setups (gpt-6 prompt cache options). Proof of which one ran is in the API's token counts.
CACHE_SETTINGS = {
    # Cache breakpoint right after the static instructions + handbook, and one cache key for every
    # vendor desk call so requests land on the server that already holds the handbook.
    "with_cache": OpenAIResponsesModelSettings(
        openai_prompt_cache_options={"mode": "implicit", "ttl": "30m"},
        openai_cache_instructions=True,
        openai_prompt_cache_key="campus-customs-vendor-desk",
    ),
    # Explicit mode with no breakpoints: OpenAI creates no new cache entry. On its own that still reads
    # entries other runs wrote, so build_agent also puts a fresh nonce at the very start of every request.
    "without_cache": OpenAIResponsesModelSettings(
        openai_prompt_cache_options={"mode": "explicit", "ttl": "30m"},
    ),
}


def build_model() -> OpenAIResponsesModel:
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to the root .env file.")
    client = AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key=api_key,
        timeout=120,  # a hung gateway call fails after 2 minutes and is retried, instead of stalling ~30 min
        max_retries=2,
        default_headers={
            "x-portkey-provider": "openai",
            # The course gateway caches whole responses: an identical request replays an old answer
            # (header x-portkey-cache-status: HIT) instead of calling the model. Force a real call every run.
            "x-portkey-cache-force-refresh": "true",
        },
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def build_agent(setup: str = "with_cache", defenses: frozenset[str] = DEFENSE_LAYERS) -> Agent[AgentDeps, VendorDecision]:
    # Instructions + the full handbook go to the model on every call.
    prompt = PROMPT_FILE if "prompt" in defenses else PROMPT_NO_DEFENSES_FILE
    static = prompt.read_text() + "\n" + HANDBOOK_FILE.read_text()
    if setup == "with_cache":
        instructions = static
    else:
        # Re-evaluated before every model request, so no two requests share a prefix to cache.
        def instructions() -> str:
            return f"Request nonce: {uuid.uuid4().hex}\n\n{static}"
    return Agent(
        build_model(),
        deps_type=AgentDeps,
        output_type=VendorDecision,
        instructions=instructions,
        tools=TOOLS,
        model_settings=OpenAIResponsesModelSettings(max_tokens=8_000, **CACHE_SETTINGS[setup]),
    )


# ---------------------------------------------------------------- design layer: rules engine

def _rows(section: str) -> list[list[str]]:
    """Table rows of one numbered handbook section, header and divider rows skipped."""
    text = HANDBOOK_FILE.read_text()
    body = text.split(f"## {section}.", 1)[1].split("\n## ", 1)[0]
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in body.splitlines() if line.startswith("|")]
    return [r for r in rows[2:] if r]


def _norm(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", name.lower()).split())


APPROVED = {_norm(r[1]): r[1] for r in _rows("5")}
REMOVED = {_norm(r[0]): r[0] for r in _rows("6")}
MAX_COST = {r[0]: float(r[4].lstrip("$").replace(",", "")) for r in _rows("9") if r[0].startswith("CC-")}
MAX_LEAD_DAYS, MAX_MIN_ORDER = 21, 600


def _lookup(vendor: str, names: dict[str, str]) -> str | None:
    n = _norm(vendor)
    for key, name in names.items():
        if n == key or (len(n) >= 6 and (key in n or n in key)):
            return name
    return None


def _numbers(text: str) -> set[float]:
    return {round(float(x.replace(",", "")), 2) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def apply_purchasing_rules(a: VendorDecision, doc_text: str) -> tuple[str, str]:
    """Handbook section 4 in code. Returns (decision, reason). The model's own decision is not used."""
    found = _numbers(doc_text)

    def missing(value) -> bool:  # unknown, or a number the document never states
        return value is None or round(float(value), 2) not in found

    if name := _lookup(a.vendor, REMOVED):
        return "do_not_recommend", f"Approved-vendor check failed: {name} is on the removed or pending vendor list."
    if not _lookup(a.vendor, APPROVED):
        return "do_not_recommend", f"Approved-vendor check failed: {a.vendor} is not on the approved vendor list."
    if a.sku not in MAX_COST:
        return "do_not_recommend", f"Price check failed: SKU {a.sku} is not in the catalogue, so there is no max unit cost."
    if missing(a.unit_price):
        return "do_not_recommend", "Price check failed: the document does not state a unit price that can be verified."
    if a.unit_price > MAX_COST[a.sku]:
        return "do_not_recommend", f"Price check failed: ${a.unit_price:.2f} is above the ${MAX_COST[a.sku]:.2f} max unit cost for {a.sku}."
    if missing(a.lead_time_days):
        return "do_not_recommend", "Lead-time check failed: the document does not state a lead time that can be verified."
    if a.lead_time_days > MAX_LEAD_DAYS:
        return "do_not_recommend", f"Lead-time check failed: {a.lead_time_days} days is over the {MAX_LEAD_DAYS}-day limit."
    if missing(a.min_order):
        return "do_not_recommend", "Minimum-order check failed: the document does not state a minimum order that can be verified."
    if a.min_order > MAX_MIN_ORDER:
        return "do_not_recommend", f"Minimum-order check failed: {a.min_order} units is over the {MAX_MIN_ORDER}-unit limit."
    return "recommend", (
        f"All four purchasing checks passed: approved vendor, ${a.unit_price:.2f} is within the "
        f"${MAX_COST[a.sku]:.2f} max for {a.sku}, {a.lead_time_days}-day lead time, {a.min_order}-unit minimum."
    )


def document_text_seen(result) -> str:
    """Everything read_document returned to the model in this run."""
    return "\n".join(
        str(part.content)
        for msg in result.all_messages()
        for part in msg.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "read_document"
    )


# ---------------------------------------------------------------- logging


def dollars(input_tokens: int, cache_read: int, cache_write: int, output_tokens: int) -> dict:
    """Cost in dollars from prices.json. Uncached input = input minus the cached parts."""
    uncached = input_tokens - cache_read - cache_write
    parts = {
        "uncached_input": uncached * PRICES["input_per_1m"] / 1e6,
        "cached_input": cache_read * PRICES["cached_input_per_1m"] / 1e6,
        "cache_write": cache_write * PRICES["cache_write_per_1m"] / 1e6,
        "output": output_tokens * PRICES["output_per_1m"] / 1e6,
    }
    parts["total"] = sum(parts.values())
    return {k: round(v, 8) for k, v in parts.items()}


def usage_entry(run_id: str, doc: Path, started: str, setup: str, defenses: frozenset[str], result) -> dict:
    u = result.usage
    per_request = [
        {
            "model": m.model_name,
            "input_tokens": m.usage.input_tokens,
            "cache_read_tokens": m.usage.cache_read_tokens,
            "cache_write_tokens": m.usage.cache_write_tokens,
            "output_tokens": m.usage.output_tokens,
            "reasoning_tokens": m.usage.details.get("reasoning_tokens", 0),
            "cost_usd": dollars(m.usage.input_tokens, m.usage.cache_read_tokens,
                                m.usage.cache_write_tokens, m.usage.output_tokens),
        }
        for m in result.all_messages()
        if isinstance(m, ModelResponse)
    ]
    return {
        "run_id": run_id,
        "document": str(doc.relative_to(ROOT)),
        "time": started,
        "model": MODEL_NAME,
        "setup": setup,
        "defenses": sorted(defenses),
        "requests": u.requests,
        "input_tokens": u.input_tokens,
        "cache_read_tokens": u.cache_read_tokens,
        "cache_write_tokens": u.cache_write_tokens,
        "output_tokens": u.output_tokens,
        "reasoning_tokens": u.details.get("reasoning_tokens", 0),
        "total_tokens": u.total_tokens,
        "cost_usd": dollars(u.input_tokens, u.cache_read_tokens, u.cache_write_tokens, u.output_tokens),
        "per_request": per_request,
    }


def audit_entry(run_id: str, doc: Path, started: str, deps: AgentDeps, result, final: VendorDecision) -> dict:
    calls, returns = {}, {}
    for msg in result.all_messages():
        for part in msg.parts:
            if isinstance(part, ToolCallPart) and part.tool_name in {t.__name__ for t in TOOLS}:
                calls[part.tool_call_id] = part
            elif isinstance(part, ToolReturnPart):
                returns[part.tool_call_id] = part
    steps = []
    for call_id, call in calls.items():
        content = str(returns[call_id].content) if call_id in returns else "(no result)"
        short = content if len(content) <= 200 else content[:200] + f"... [{len(content)} chars total]"
        steps.append({"tool": call.tool_name, "args": call.args_as_dict(), "result": short})
    return {
        "run_id": run_id,
        "document": str(doc.relative_to(ROOT)),
        "time": started,
        "defenses": sorted(deps.defenses),
        "hidden_text_removed": deps.hidden_removed,
        "tool_calls": steps,
        "model_answer": result.output.model_dump(),
        "final_answer": final.model_dump(),
    }


# ---------------------------------------------------------------- main

def run(doc: Path, setup: str = "with_cache", defenses: frozenset[str] = DEFENSE_LAYERS) -> tuple[VendorDecision, dict]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    if not TRAP_LOG.exists():
        TRAP_LOG.write_text("[]")

    run_id = uuid.uuid4().hex[:8]
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    deps = AgentDeps(run_id=run_id, doc_path=doc, defenses=frozenset(defenses))

    result = build_agent(setup, deps.defenses).run_sync(
        f"Review this vendor document: {doc}",
        deps=deps,
        usage_limits=UsageLimits(request_limit=MAX_REQUESTS_PER_RUN),
    )

    final = result.output
    if "design" in deps.defenses:
        decision, reason = apply_purchasing_rules(final, document_text_seen(result))
        final = final.model_copy(update={"decision": decision, "reason": reason})

    usage = usage_entry(run_id, doc, started, setup, deps.defenses, result)
    usage["hidden_text_removed"] = len(deps.hidden_removed)
    append_json(USAGE_LOG, usage)
    append_json(AUDIT_LOG, audit_entry(run_id, doc, started, deps, result, final))

    print(json.dumps(final.model_dump(), indent=2))
    layers = ",".join(sorted(deps.defenses)) or "none"
    print(
        f"\n[{run_id} {setup} defenses={layers}] {usage['requests']} requests | input {usage['input_tokens']:,} "
        f"(cache read {usage['cache_read_tokens']:,}, cache write {usage['cache_write_tokens']:,}) | output {usage['output_tokens']:,} | "
        f"cost ${usage['cost_usd']['total']:.6f}"
    )
    return final, usage


def main() -> None:
    parser = argparse.ArgumentParser(description="Campus Customs vendor desk agent")
    parser.add_argument("--doc", required=True, help="path to one vendor document (.html, .pdf, or .eml)")
    parser.add_argument("--no-cache", action="store_true", help="turn off prompt caching for this run")
    parser.add_argument("--no-defenses", action="store_true", help="run the Problem 3 agent with no defenses")
    parser.add_argument("--defenses", default="code,design,prompt",
                        help="comma-separated defense layers to turn on (code, design, prompt)")
    args = parser.parse_args()
    defenses = frozenset() if args.no_defenses else frozenset(filter(None, args.defenses.split(",")))
    if unknown := defenses - DEFENSE_LAYERS:
        parser.error(f"unknown defense layer(s): {sorted(unknown)}")
    doc = Path(args.doc).resolve()
    if not doc.is_file():
        parser.error(f"document not found: {args.doc}")
    run(doc, "without_cache" if args.no_cache else "with_cache", defenses)


if __name__ == "__main__":
    main()
