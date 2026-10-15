# Campus Customs Vendor Desk Agent (HW6)

A PydanticAI agent that reads one vendor document (HTML quote, PDF, or `.eml` email), pulls out the vendor,
SKU, unit price, lead time, and minimum order, and recommends (or not) following the Campus Customs Shop
Handbook. It uses `gpt-6-luna` only, through Portkey. Yale MGT 409, AI Foundations for Managers.

**Results page:** open `output/hw6_report.html` (one self-contained file, works offline).

## How to run the agent

Requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your PORTKEY_API_KEY in .env
```

Run it on one document:

```bash
python agent.py --doc data/practice_docs/p01_bluehen_quote.html                 # final agent, all defenses
python agent.py --doc data/practice_docs/p01_bluehen_quote.html --no-defenses   # the undefended Problem 3 agent
python agent.py --doc data/exam_docs/e09_email.eml --defenses code,prompt       # any subset of code,design,prompt
python agent.py --doc data/practice_docs/p01_bluehen_quote.html --no-cache      # turn off prompt caching
```

It prints the answer as JSON and appends to `output/usage_log.json` (tokens and dollars) and
`output/audit_trail.json` (tool calls and the final answer). The trap tools `send_email` and `approve_payment`
never send or pay anything. They only write to `output/trap_calls.json`, which should stay `[]`.

To rerun a whole problem: `scripts/cache_test.py` (Problem 4), `scripts/attack_test.py` (Problem 5),
`scripts/defense_test.py` (Problem 6), `scripts/exam_run.py` (Problem 8), `scripts/build_report.py`
(Problem 9, rebuilds the report from `output/`).

## Files

| Path | What it is |
|---|---|
| `agent.py` | Entry point: model, caching setups, defense switches, the design-layer rules engine, logging |
| `tools.py` | `read_document` (raw and visible-text-only readers) and the trap tools behind a human sign-off gate |
| `models.py` | `VendorDecision` output type and run settings |
| `prompts/prompt.md` | Instructions with security rules (the handbook is appended on every call) |
| `prompts/prompt_no_defenses.md` | The original Problem 3 prompt, used by `--no-defenses` |
| `data/` | Course data: handbook, prices, 12 practice docs plus key, 10 exam docs. `my_attacks/` is empty (Problem 7 not completed; see `output/red_team.md`) |
| `output/` | Every result file and write-up; `harness.md` explains the agent's harness and Safety layers |
| `AI_prompts.md` | Log of the prompts I typed into my vibe coder, one section per problem |

Never commit `.env`. It is in `.gitignore`. Campus Customs is used as a class setting only; all vendors
and documents are made up.
