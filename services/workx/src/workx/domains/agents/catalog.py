"""Curated Skills and model tiers offered to workmates.

Skills are reviewed Agent SDK plugins shipped in the runtime release (runtime/skills, Part 4 §4); this catalog
is what the UI may attach. Model tiers follow decision D-01 (Claude tiers only); the model gateway maps a tier
to a concrete model ID per deployment (P-05).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    category: str


SKILLS: tuple[Skill, ...] = (
    Skill("slides", "Slides", "Builds presentation decks (.pptx) from an outline or a document.", "Office"),
    Skill("deep-research", "Deep Research", "Plans searches, reads sources and writes a cited report.", "Research"),
    Skill("data-visualization", "Data Visualization", "Turns tables into charts and short findings.", "Data"),
    Skill("product-prototype", "Product Prototype", "Drafts clickable HTML prototypes from requirements.", "Design"),
    Skill("office", "Office", "Creates and edits documents and spreadsheets (.docx, .xlsx).", "Office"),
    Skill("image", "Image", "Prepares images and diagrams for documents and slides.", "Design"),
)
SKILL_IDS = {s.id for s in SKILLS}
SKILL_BY_NAME = {s.name.lower(): s.id for s in SKILLS}


@dataclass(frozen=True)
class ModelTier:
    id: str
    label: str


MODEL_TIERS: tuple[ModelTier, ...] = (
    ModelTier("auto", "Auto"),
    ModelTier("opus", "Claude Opus"),
    ModelTier("sonnet", "Claude Sonnet"),
    ModelTier("haiku", "Claude Haiku"),
)
MODEL_TIER_IDS = {m.id for m in MODEL_TIERS}


def normalize_skill(value: str) -> str | None:
    key = value.strip()
    if key in SKILL_IDS:
        return key
    return SKILL_BY_NAME.get(key.lower())
