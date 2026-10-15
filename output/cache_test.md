# Cache Test: With vs. Without Cached Tokens

All 12 practice documents, run once per setup with `gpt-6-luna` (`python scripts/cache_test.py`).
Each document takes **2 model calls**: call 1 reads the document with the tool, and call 2 returns the
answer. That makes 24 calls per setup and 48 in total. Every call, with every token count the API
reported, is saved in `output/cache_test.json`.

## The two setups

| Setup | How it is configured (`agent.py`, `CACHE_SETTINGS`) |
|---|---|
| **with_cache** | Instructions + handbook stay byte-for-byte identical on every call. `openai_cache_instructions=True` puts a cache breakpoint right after the handbook. `prompt_cache_key="campus-customs-vendor-desk"` sends every call to the same cache. |
| **without_cache** | `prompt_cache_options.mode="explicit"` with no breakpoints, **plus** a fresh random nonce at the very start of every request, so no two requests share a prefix. |

**Proof from the API's own numbers:**

| | without_cache | with_cache |
|---|---|---|
| Calls | 24 | 24 |
| Calls with `cached_tokens > 0` | **0** | **19** |
| Total `cached_tokens` (cache reads) | **0** | **204,623** |
| Total `cache_write_tokens` | 261,862 | 56,690 |

The without_cache setup shows **0 cached tokens on all 24 calls**, so it counts.

My first try at without_cache used explicit mode alone. That test run (p02) still showed 21,546 cached
tokens, because explicit mode only stops *new* cache entries; it still reads entries that earlier runs
wrote. That run does not count. The per-request nonce fixed it.

## Results

| | without_cache | with_cache | Saved |
|---|---|---|---|
| **Total cost, 12 documents** | **$0.034268** | **$0.010996** | **$0.023272 (67.9%)** |
| **Cost per document** | **$0.002856** | **$0.000916** | $0.001940 |
| Input tokens | 264,886 | 264,337 | |
| Output tokens (incl. reasoning) | 2,465 | 3,123 | |

Where the without_cache money went: $0.032733 cache writes, $0.000302 uncached input, $0.001233 output.
Where the with_cache money went: $0.007086 cache writes, $0.002046 cached reads, $0.000302 uncached input,
$0.001561 output.

**Steady state:** 7 of the 12 with_cache documents hit the cache on *both* calls. Those cost
**$0.000373 per document, 86.9% less** than without_cache. The 67.9% overall figure is lower because
5 of the 24 calls missed the cache (see surprises below).

Accuracy was unaffected by caching. Both setups missed the same injected documents (p02, p07, p12).
p03 was also fooled in the without_cache run only. That is a safety problem for later, not a caching
effect.

## Real numbers vs. my Problem 2 estimate

| | Problem 2 estimate | Real | Why different |
|---|---|---|---|
| Tokens per call | 10,058 (handbook only) | 10,919–11,252 input | +~880 tokens: prompt.md instructions, the 3 tool definitions, the output schema, and the user message. On call 2, also the document text. |
| Calls per document | 1 (assumed) | **2** | The agent calls `read_document`, then answers, so the handbook goes out **twice** per document. |
| No-cache price per handbook token | $0.10 / 1M (input) | **$0.125 / 1M** (cache write) | The API writes the prompt to cache on every call, even with caching turned off (surprise 1). |
| 1 call, no cache | $0.0010058 | $0.00139 to $0.00151 | |
| 1 call, cache hit | $0.0001006 | $0.000150 to $0.000244 | Extra: a few new tokens written each call, 126 uncached tokens, and output. |
| **1,000 documents, no cache** | $1.0058 (per 1,000 calls) | **$2.856** | 2 calls × 1.25 write price × 1.09 extra tokens ≈ 2.7×, plus output |
| **1,000 documents, with cache** | $0.1017 (per 1,000 calls) | **$0.916** observed / **$0.373** steady state | 2 calls, cache misses, and output |

The **token count** held up: 10,058 handbook tokens out of a ~10,800-token cached prefix. The **cost per
document** was off by about 3×. Problem 2 priced "one call that sends the handbook," but a real
document takes two calls, and without caching every handbook token is billed at the write price.
The **savings percentage** (estimated 90%) came out close to the steady-state 86.9%.

## Projection: 1,000 documents a day for 30 days (30,000 documents)

| Setup | Per document | 30-day cost |
|---|---|---|
| Without cache | $0.002856 | **$85.67** |
| With cache, at this test's hit rate (19 of 24 calls) | $0.000916 | **$27.49** |
| With cache, steady state (every call hits) | $0.000373 | **$11.19** |

At 1,000 documents a day, a call arrives about every 1.5 minutes even if spread over 24 hours, well inside the 30-minute cache window.
So the real bill should land near the steady-state **$11 a month**, a saving of about **$74 a month,
or 87%**.

## What surprised me, and why it happens

1. **"No cache" costs *more* than the plain input price.** Every without_cache call reported about
   10,800 `cache_write_tokens`, even with no breakpoints set. gpt-6-luna writes each prompt to the cache
   whether or not it will ever be read, and writing costs $0.125 per 1M, 25% *more* than normal input
   ($0.10). So turning caching off does not just give up the discount: you pay a premium to save a cache
   you never reuse. The only ways to avoid it are to reuse the cache or to keep prompts short.

2. **The handbook is sent twice per document.** Problem 2 thought in "calls," but the agent makes a tool
   call and then a second call to answer. Both carry the full handbook. Caching matters even more
   because of this, since call 2 almost always hits the cache that call 1 just wrote.

3. **Cache hits are not guaranteed, even with caching on.** 5 of the 24 with_cache calls missed:
   - p01 call 1: expected, nothing was cached yet.
   - p04 call 2: the call that took 284 seconds.
   - p09 call 2.
   - p11 and p12 call 1.
   Caches live on individual servers and are best-effort. A request that is slow, retried, or sent to
   a different server misses, even with the same cache key. Each miss costs about 9× a hit
   ($0.00139 vs. $0.00015), which is why the overall saving was 68% instead of 87%.

4. **The cache works in fixed 128-token blocks, and the last 126 tokens are never cached.** Call 1 reads
   exactly **10,752** cached tokens every time (84 × 128). Every call, in both setups, has exactly
   **126** uncached tokens: the tail of the prompt (the user message) after the last full block. Call 2
   reads 10,794 tokens, which is the explicit breakpoint right after the handbook.

5. **Output barely matters, even at 5× the price.** Output is $0.50 per 1M vs. $0.10 for input, but each
   call writes only about 50–230 tokens. That is 4% of the no-cache bill and 14% of the cached bill.
   One outlier: p09 with_cache call 2 spent 735 reasoning tokens. That added
   about $0.0004 of output, roughly 2× a normal cache hit, on top of that call also missing the cache.
