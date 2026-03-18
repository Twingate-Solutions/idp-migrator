"""Fuzzy group-name matching for twingate-idp-migrator.

Matches "From" groups (old IdP) to "To" groups (new IdP) using
rapidfuzz token_sort_ratio scoring with configurable threshold.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from src.models import GroupMapping, TwingateGroup
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Common prefixes stripped before comparison (case-insensitive)
_STRIP_PREFIXES = re.compile(
    r"^(?:sg[-_]|grp[-_]|tg[-_]|group[-_]|grp\.|sg\.)",
    flags=re.IGNORECASE,
)

DEFAULT_THRESHOLD = 0.6


def _normalize(name: str) -> str:
    """Normalize a group name for fuzzy comparison.

    Strips leading/trailing whitespace, lowercases, and removes
    common IdP-specific prefixes (sg-, grp-, tg-, group-).

    Args:
        name: Raw group display name.

    Returns:
        Normalized name string.
    """
    name = name.strip().lower()
    return _STRIP_PREFIXES.sub("", name).strip()


def match_groups(
    from_groups: list[TwingateGroup],
    to_groups: list[TwingateGroup],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[GroupMapping]:
    """Fuzzy-match each from_group to the best to_group by name similarity.

    Algorithm:
    1. Normalize all names (lowercase, strip prefixes).
    2. For each from_group, find the best scoring to_group using
       token_sort_ratio (handles word reordering).
    3. If score >= threshold, create a mapping with confidence = score / 100.
    4. Resolve conflicts: if two from_groups match the same to_group,
       keep the higher-confidence match; mark the other as unmatched.
    5. Return sorted: matched (by confidence desc) then unmatched.

    Args:
        from_groups: Old-IdP groups to map from.
        to_groups: New-IdP groups to map to.
        threshold: Minimum match score (0.0–1.0). Default 0.6.

    Returns:
        List of GroupMapping, sorted matched-first by confidence desc.
    """
    if not from_groups or not to_groups:
        return [GroupMapping(from_group=g) for g in from_groups]

    to_names_normalized = [_normalize(g.name) for g in to_groups]

    # Build initial matches: from_group → (to_group, confidence)
    raw: dict[str, tuple[TwingateGroup, float]] = {}  # keyed by from_group.id
    for from_g in from_groups:
        norm_from = _normalize(from_g.name)
        result = process.extractOne(
            norm_from,
            to_names_normalized,
            scorer=fuzz.token_sort_ratio,
        )
        if result is not None:
            _match_str, score, idx = result
            confidence = score / 100.0
            if confidence >= threshold:
                raw[from_g.id] = (to_groups[idx], confidence)

    # Conflict resolution: each to_group can only be claimed once.
    # Among competing from_groups, the highest confidence wins.
    claimed: dict[str, str] = {}  # to_group.id → from_group.id (winner)
    for from_id, (to_g, conf) in raw.items():
        existing_winner = claimed.get(to_g.id)
        if existing_winner is None:
            claimed[to_g.id] = from_id
        else:
            _, existing_conf = raw[existing_winner]
            if conf > existing_conf:
                claimed[to_g.id] = from_id  # new winner displaces old

    # Build final mappings
    mappings: list[GroupMapping] = []
    for from_g in from_groups:
        match = raw.get(from_g.id)
        if match is not None:
            to_g, conf = match
            # Only include if this from_group won the claim
            if claimed.get(to_g.id) == from_g.id:
                mappings.append(
                    GroupMapping(from_group=from_g, to_group=to_g, confidence=conf)
                )
                continue
        # Unmatched (no match found, below threshold, or lost conflict)
        mappings.append(GroupMapping(from_group=from_g))

    # Sort: matched (has to_group) by confidence desc, then unmatched
    matched = sorted(
        [m for m in mappings if m.to_group is not None],
        key=lambda m: m.confidence,
        reverse=True,
    )
    unmatched = [m for m in mappings if m.to_group is None]

    logger.info(
        "groups_matched",
        from_count=len(from_groups),
        to_count=len(to_groups),
        matched=len(matched),
        unmatched=len(unmatched),
        threshold=threshold,
    )
    return matched + unmatched
