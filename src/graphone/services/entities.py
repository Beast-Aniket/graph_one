import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from graphone.models import CanonicalEntity


SUFFIXES = re.compile(r"\b(incorporated|inc|llc|ltd|limited|corp|corporation|company|co|gmbh|plc|pbc)\b", re.I)
PUNCTUATION = re.compile(r"[.,&()\[\]{}\-–—_]+")


def normalize_name(name: str) -> str:
    compact = PUNCTUATION.sub(" ", name.strip().lower())
    compact = SUFFIXES.sub(" ", compact)
    return " ".join(compact.split())


@dataclass(frozen=True)
class Resolution:
    raw_name: str
    normalized_name: str
    canonical_name: str
    canonical_key: str
    confidence: float
    method: str
    needs_review: bool


async def resolve_entity(session: AsyncSession, raw_name: str) -> Resolution:
    normalized = normalize_name(raw_name)
    entities = (await session.scalars(select(CanonicalEntity))).all()
    closest: tuple[CanonicalEntity, float] | None = None
    for entity in entities:
        candidates = [entity.canonical_name, *entity.aliases]
        if normalized in {normalize_name(candidate) for candidate in candidates}:
            exact = normalized == normalize_name(entity.canonical_name)
            return Resolution(raw_name, normalized, entity.canonical_name, entity.canonical_key, 1.0, "EXACT" if exact else "SEED_ALIAS", False)
        score = SequenceMatcher(a=normalized, b=entity.canonical_key).ratio()
        if closest is None or score > closest[1]:
            closest = (entity, score)
    if closest and closest[1] >= 0.85:
        entity, score = closest
        return Resolution(raw_name, normalized, entity.canonical_name, entity.canonical_key, round(score, 4), "CONSERVATIVE_MATCH", True)
    return Resolution(raw_name, normalized, raw_name, normalized, 0.0, "CONSERVATIVE_MATCH", False)

