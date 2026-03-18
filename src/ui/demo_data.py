"""Pre-built sample data for the TEST-mode walkthrough.

Simulates an Okta → Entra ID migration scenario with five group pairs,
several shared resources, and a mix of high/medium/low match confidence.
"""

from __future__ import annotations

from src.models import (
    AccessEdge,
    AccessPolicy,
    AccessPolicyMode,
    GroupMapping,
    GroupType,
    SecurityPolicyRef,
    TwingateGroup,
    TwingateResource,
)

# ---------------------------------------------------------------------------
# Groups — five "old" Okta groups and five "new" Entra groups.
# Entra-Sales-Team intentionally has a slightly different name so the
# matcher shows a medium-confidence suggestion for Okta-Sales.
# Entra-Executive has no Okta counterpart, so it stays in Available.
# Okta-HR has no close Entra match, demonstrating an unmapped/low-confidence row.
# ---------------------------------------------------------------------------

def _group(gid: str, name: str, origin_id: str) -> TwingateGroup:
    return TwingateGroup(
        id=gid, name=name, type=GroupType.SYNCED, origin_id=origin_id, is_active=True
    )


DEMO_GROUPS: list[TwingateGroup] = [
    # Old IdP (Okta)
    _group("old-eng",    "Okta-Engineering", "okta-1"),
    _group("old-fin",    "Okta-Finance",     "okta-2"),
    _group("old-devops", "Okta-DevOps",      "okta-3"),
    _group("old-sales",  "Okta-Sales",       "okta-4"),
    _group("old-hr",     "Okta-HR",          "okta-5"),
    # New IdP (Entra ID)
    _group("new-eng",    "Entra-Engineering", "entra-1"),
    _group("new-fin",    "Entra-Finance",     "entra-2"),
    _group("new-devops", "Entra-DevOps",      "entra-3"),
    _group("new-sales",  "Entra-Sales-Team",  "entra-4"),
    _group("new-exec",   "Entra-Executive",   "entra-5"),
]

# ---------------------------------------------------------------------------
# Security policies referenced by access edges
# ---------------------------------------------------------------------------

_MFA = SecurityPolicyRef(id="pol-mfa", name="MFA Required")
_STD = SecurityPolicyRef(id="pol-std", name="Standard Access")


def _edge(principal_id: str, policy: SecurityPolicyRef | None = None) -> AccessEdge:
    """Build an access edge for the given group ID."""
    return AccessEdge(
        principal_id=principal_id,
        security_policy=policy,
        expires_at=None,
        access_policy=AccessPolicy(mode=AccessPolicyMode.MANUAL),
    )


# ---------------------------------------------------------------------------
# Resources — eight internal services with overlapping group access.
# This produces ~20 planned actions in the dry-run preview.
# ---------------------------------------------------------------------------

# Pre-built From/To sets and confirmed mappings for demo mode.
# Okta groups are the "old IdP" (From), Entra groups are the "new IdP" (To).
# Used to seed AppState so the full wizard is walkable without manual Step 2.

DEMO_FROM_GROUPS: list[TwingateGroup] = [g for g in DEMO_GROUPS if g.id.startswith("old-")]
DEMO_TO_GROUPS: list[TwingateGroup] = [g for g in DEMO_GROUPS if g.id.startswith("new-")]


def _by_id(groups: list[TwingateGroup], gid: str) -> TwingateGroup:
    """Return the group with the given ID, raising StopIteration if not found."""
    return next(g for g in groups if g.id == gid)


DEMO_MAPPINGS: list[GroupMapping] = [
    GroupMapping(
        from_group=_by_id(DEMO_FROM_GROUPS, "old-eng"),
        to_group=_by_id(DEMO_TO_GROUPS, "new-eng"),
        confidence=0.92,
        is_confirmed=True,
    ),
    GroupMapping(
        from_group=_by_id(DEMO_FROM_GROUPS, "old-fin"),
        to_group=_by_id(DEMO_TO_GROUPS, "new-fin"),
        confidence=0.88,
        is_confirmed=True,
    ),
    GroupMapping(
        from_group=_by_id(DEMO_FROM_GROUPS, "old-devops"),
        to_group=_by_id(DEMO_TO_GROUPS, "new-devops"),
        confidence=0.90,
        is_confirmed=True,
    ),
    GroupMapping(
        from_group=_by_id(DEMO_FROM_GROUPS, "old-sales"),
        to_group=_by_id(DEMO_TO_GROUPS, "new-sales"),
        confidence=0.65,
        is_confirmed=True,
    ),
    GroupMapping(
        from_group=_by_id(DEMO_FROM_GROUPS, "old-hr"),
        to_group=None,
        confidence=0.0,
        is_confirmed=False,
    ),
]


DEMO_RESOURCES: list[TwingateResource] = [
    TwingateResource(
        id="res-db", name="prod-database.corp", address="10.0.1.10", is_active=True,
        access_edges=[_edge("old-eng", _MFA), _edge("old-devops", _MFA)],
    ),
    TwingateResource(
        id="res-wiki", name="internal-wiki.corp", address="10.0.1.20", is_active=True,
        access_edges=[_edge("old-eng"), _edge("old-fin"), _edge("old-hr")],
    ),
    TwingateResource(
        id="res-gitlab", name="gitlab.corp", address="10.0.1.30", is_active=True,
        access_edges=[_edge("old-eng", _MFA), _edge("old-devops", _MFA)],
    ),
    TwingateResource(
        id="res-jira", name="jira.corp", address="10.0.1.40", is_active=True,
        access_edges=[_edge("old-eng"), _edge("old-fin"), _edge("old-sales")],
    ),
    TwingateResource(
        id="res-sf", name="salesforce.corp", address="10.0.2.10", is_active=True,
        access_edges=[_edge("old-sales"), _edge("old-fin")],
    ),
    TwingateResource(
        id="res-hr", name="hr-portal.corp", address="10.0.2.20", is_active=True,
        access_edges=[_edge("old-hr", _STD)],
    ),
    TwingateResource(
        id="res-mon", name="monitoring.corp", address="10.0.1.50", is_active=True,
        access_edges=[_edge("old-devops", _MFA)],
    ),
    TwingateResource(
        id="res-ci", name="ci-runner.corp", address="10.0.1.60", is_active=True,
        access_edges=[_edge("old-devops", _MFA), _edge("old-eng", _MFA)],
    ),
]
