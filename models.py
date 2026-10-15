"""Structured types and fixed settings for the Campus Customs vendor desk agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

MODEL_NAME = "gpt-6-luna"  # the only model allowed in this assignment
MAX_REQUESTS_PER_RUN = 6  # model round-trips per document before the run is stopped
DEFENSE_LAYERS = frozenset({"code", "design", "prompt"})  # Problem 6; frozenset() = Problem 3 agent

Decision = Literal["recommend", "do_not_recommend"]


class VendorDecision(BaseModel):
    """What the vendor desk agent reports for one vendor document (handbook section 13)."""

    vendor: str = Field(description="Vendor company name exactly as the document gives it.")
    sku: str | None = Field(description="Campus Customs SKU, e.g. CC-HD-006. null if the document does not say.")
    unit_price: float | None = Field(description="Quoted price per unit in US dollars. null if the document does not say.")
    lead_time_days: int | None = Field(description="Lead time in days, as stated in the document. null if not stated.")
    min_order: int | None = Field(description="Minimum order in units. null if the document does not say.")
    decision: Decision = Field(description="recommend only if all four handbook purchasing checks pass.")
    reason: str = Field(description="One sentence naming the purchasing check that decided it.")


@dataclass
class AgentDeps:
    """Per-run context handed to every tool."""

    run_id: str
    doc_path: Path  # the one document this run is allowed to read
    defenses: frozenset[str] = DEFENSE_LAYERS
    human_signoff: bool = False  # a document review never has one; only a person can grant it
    hidden_removed: list[dict] = field(default_factory=list)  # filled by the code layer
