# Handbook Size and Cost Estimate

The Campus Customs Shop Handbook (`data/shop_handbook.md`) goes out to `gpt-6-luna` on every vendor desk call.
This file estimates its size and what it costs. Problem 4 checks these numbers against real runs.

## 1. Token count: **10,058 tokens**

**How I got it:**

- I counted with OpenAI's `tiktoken` library and the `o200k_base` encoding, the tokenizer used by current
  OpenAI GPT models. Script: `scripts/count_tokens.py` (run with `.venv/bin/python scripts/count_tokens.py`).
- Raw size: 338 lines, 6,127 words, 28,903 characters.
- Sanity check: as a cross-check, the older `cl100k_base` encoding gives 10,184 tokens, within about 1%.
  The usual "4 characters per token" rule would guess only about 7,200. This handbook runs denser
  (about 2.9 characters per token) because most of it is tables: SKUs like `CC-HD-006`, dollar amounts,
  dates, and `|` separators each break into several short tokens.
- This matches the assignment's "about 10,000 tokens."

**Caveat for Problem 4:** the real API bill counts a few more input tokens than the handbook alone:
message wrapper tokens, the agent's own instructions, and the vendor document itself. So the real
`prompt_tokens` per call should be somewhat above 10,058.

## 2. What the handbook alone costs

Prices from `data/prices.json` (gpt-6-luna, per 1M tokens):

| Token type | Price per 1M | Price per token |
|---|---|---|
| Input (not cached) | $0.10 | $0.0000001 |
| Cached input (cache read) | $0.01 | $0.00000001 |
| Cache write | $0.125 | $0.000000125 |

Formula: **cost = tokens × (price per 1M) ÷ 1,000,000**

### One call

| Scenario | Math | Cost |
|---|---|---|
| Without caching | 10,058 × $0.10 ÷ 1,000,000 | **$0.0010058** (about 0.1¢) |
| With caching, first call (cache write) | 10,058 × $0.125 ÷ 1,000,000 | **$0.0012573** |
| With caching, later calls (cache hit) | 10,058 × $0.01 ÷ 1,000,000 | **$0.0001006** (about 0.01¢) |

The first cached call costs 25% *more* than an uncached one because the cache has to be written. Every
call after that costs one tenth as much.

### 1,000 calls

**Without caching:** each call pays full input price.

> 1,000 × 10,058 = 10,058,000 tokens
> 10,058,000 × $0.10 ÷ 1,000,000 = **$1.0058**

**With caching:** the first call writes the cache, and the other 999 read it.

> Cache write: 10,058 × $0.125 ÷ 1,000,000 = $0.0012573
> Cache reads: 999 × 10,058 = 10,047,942 tokens × $0.01 ÷ 1,000,000 = $0.1004794
> Total = $0.0012573 + $0.1004794 = **$0.1017**

### Summary

| | 1 call | 1,000 calls |
|---|---|---|
| Without caching | $0.0010058 | **$1.0058** |
| With caching | $0.0012573 (write) / $0.0001006 (hit) | **$0.1017** |
| **Savings** | | **$0.9041 (about 90%)** |

**Assumptions:**

- Caching only works if the handbook is an identical prefix at the very start of every prompt,
  before the vendor document.
- Caches expire after a period with no calls. If the 1,000 calls are spread out, the cache gets
  rewritten more than once and the real total lands a bit above $0.1017. If every call misses the
  cache, the total climbs back toward $1.0058.
- These numbers cover the handbook only. Output tokens ($0.50 per 1M) and the vendor document tokens
  are extra.
