"""Count the tokens in the shop handbook and price it with data/prices.json."""
import json
from pathlib import Path

import tiktoken

ROOT = Path(__file__).resolve().parent.parent
handbook = (ROOT / "data" / "shop_handbook.md").read_text()
prices = json.loads((ROOT / "data" / "prices.json").read_text())["gpt-6-luna"]

tokens = len(tiktoken.get_encoding("o200k_base").encode(handbook))
per_m = lambda rate: tokens * rate / 1_000_000

uncached = per_m(prices["input_per_1m"])
cached = per_m(prices["cached_input_per_1m"])
write = per_m(prices["cache_write_per_1m"])

print(f"characters: {len(handbook):,}  tokens (o200k_base): {tokens:,}")
print(f"1 call   uncached ${uncached:.7f} | cache write ${write:.7f} | cached read ${cached:.7f}")
print(f"1000 calls uncached ${uncached * 1000:.4f} | cached (1 write + 999 reads) ${write + cached * 999:.4f}")
