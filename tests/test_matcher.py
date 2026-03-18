"""Unit tests for src/core/matcher.py."""

from __future__ import annotations

import pytest

from src.core.matcher import DEFAULT_THRESHOLD, _normalize, match_groups
from src.models import GroupType, TwingateGroup

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _group(id: str, name: str) -> TwingateGroup:
    return TwingateGroup(id=id, name=name, type=GroupType.SYNCED)


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

def test_normalize_lowercase() -> None:
    assert _normalize("Engineering") == "engineering"


def test_normalize_strips_whitespace() -> None:
    assert _normalize("  Engineering  ") == "engineering"


def test_normalize_strips_sg_prefix() -> None:
    assert _normalize("sg-Engineering") == "engineering"


def test_normalize_strips_grp_prefix() -> None:
    assert _normalize("grp-Finance") == "finance"


def test_normalize_strips_tg_prefix() -> None:
    assert _normalize("tg-DevOps") == "devops"


def test_normalize_strips_group_prefix() -> None:
    assert _normalize("group-Sales") == "sales"


def test_normalize_no_prefix_unchanged() -> None:
    assert _normalize("Engineering") == "engineering"


# ---------------------------------------------------------------------------
# match_groups — basic matching
# ---------------------------------------------------------------------------

def test_exact_match_after_normalization() -> None:
    """Identical names (different case) get confidence 1.0."""
    from_groups = [_group("f1", "Engineering")]
    to_groups = [_group("t1", "Engineering")]
    mappings = match_groups(from_groups, to_groups)
    assert len(mappings) == 1
    assert mappings[0].to_group is not None
    assert mappings[0].to_group.id == "t1"
    assert mappings[0].confidence == pytest.approx(1.0)


def test_high_similarity_match() -> None:
    """Names with common prefix differences get matched."""
    from_groups = [_group("f1", "Okta-Engineering")]
    to_groups = [_group("t1", "Entra-Engineering")]
    mappings = match_groups(from_groups, to_groups)
    assert mappings[0].to_group is not None
    assert mappings[0].confidence > DEFAULT_THRESHOLD


def test_below_threshold_returns_unmatched() -> None:
    """Completely different names fall below threshold."""
    from_groups = [_group("f1", "Alpha")]
    to_groups = [_group("t1", "Zephyr")]
    mappings = match_groups(from_groups, to_groups)
    assert mappings[0].to_group is None
    assert mappings[0].confidence == 0.0


def test_multiple_from_groups_matched() -> None:
    """Each from_group gets its own best match."""
    from_groups = [_group("f1", "Engineering"), _group("f2", "Finance")]
    to_groups = [_group("t1", "Engineering"), _group("t2", "Finance")]
    mappings = match_groups(from_groups, to_groups)
    matched = [m for m in mappings if m.to_group is not None]
    assert len(matched) == 2


def test_empty_from_groups_returns_empty() -> None:
    mappings = match_groups([], [_group("t1", "Engineering")])
    assert mappings == []


def test_empty_to_groups_all_unmatched() -> None:
    from_groups = [_group("f1", "Engineering")]
    mappings = match_groups(from_groups, [])
    assert len(mappings) == 1
    assert mappings[0].to_group is None


# ---------------------------------------------------------------------------
# match_groups — conflict resolution
# ---------------------------------------------------------------------------

def test_conflict_higher_confidence_wins() -> None:
    """When two from_groups match the same to_group, higher confidence wins."""
    # f1 matches t1 perfectly; f2 is similar but less so
    from_groups = [_group("f1", "Engineering"), _group("f2", "Engrneering")]  # typo
    to_groups = [_group("t1", "Engineering")]
    mappings = match_groups(from_groups, to_groups)

    matched = [m for m in mappings if m.to_group is not None]
    unmatched = [m for m in mappings if m.to_group is None]

    # Exactly one winner
    assert len(matched) == 1
    assert matched[0].from_group.id == "f1"  # f1 has perfect match
    assert len(unmatched) == 1
    assert unmatched[0].from_group.id == "f2"


# ---------------------------------------------------------------------------
# match_groups — sort order
# ---------------------------------------------------------------------------

def test_sorted_matched_first_by_confidence_desc() -> None:
    """Matched mappings come first, sorted by confidence descending."""
    from_groups = [
        _group("f1", "Alpha"),     # no match
        _group("f2", "Finance"),   # high confidence
        _group("f3", "Okta-Engineering"),  # moderate confidence
    ]
    to_groups = [_group("t1", "Finance"), _group("t2", "Engineering")]
    mappings = match_groups(from_groups, to_groups)

    # All matched first
    matched = [m for m in mappings if m.to_group is not None]
    unmatched = [m for m in mappings if m.to_group is None]
    assert mappings.index(matched[0]) < mappings.index(unmatched[0])

    # Matched are sorted by confidence desc
    if len(matched) > 1:
        for i in range(len(matched) - 1):
            assert matched[i].confidence >= matched[i + 1].confidence


# ---------------------------------------------------------------------------
# match_groups — custom threshold
# ---------------------------------------------------------------------------

def test_custom_threshold_zero_matches_everything() -> None:
    """threshold=0 forces all groups to be matched (to best available)."""
    from_groups = [_group("f1", "Alpha")]
    to_groups = [_group("t1", "Zephyr")]
    mappings = match_groups(from_groups, to_groups, threshold=0.0)
    # With threshold=0, even poor matches are accepted
    assert mappings[0].to_group is not None


def test_custom_threshold_one_matches_only_exact() -> None:
    """threshold=1.0 only matches identical normalized names."""
    from_groups = [_group("f1", "Engineering"), _group("f2", "Okta-Engineering")]
    to_groups = [_group("t1", "Engineering")]
    mappings = match_groups(from_groups, to_groups, threshold=1.0)
    matched = [m for m in mappings if m.to_group is not None]
    assert len(matched) == 1
    assert matched[0].from_group.id == "f1"
