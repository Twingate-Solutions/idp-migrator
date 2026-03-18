"""Unit tests for src/core/planner.py."""

from __future__ import annotations

from src.core.planner import build_plan
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
# Helpers
# ---------------------------------------------------------------------------

def _group(id: str, name: str) -> TwingateGroup:
    return TwingateGroup(id=id, name=name, type=GroupType.SYNCED)


def _resource(id: str, name: str, access_edges: list[AccessEdge] | None = None) -> TwingateResource:
    return TwingateResource(id=id, name=name, access_edges=access_edges or [])


def _edge(
    principal_id: str,
    policy_id: str | None = None,
    policy_name: str | None = None,
    mode: AccessPolicyMode = AccessPolicyMode.MANUAL,
) -> AccessEdge:
    return AccessEdge(
        principal_id=principal_id,
        security_policy=SecurityPolicyRef(id=policy_id, name=policy_name)
        if policy_id and policy_name
        else None,
        access_policy=AccessPolicy(mode=mode),
    )


def _confirmed_mapping(from_group: TwingateGroup, to_group: TwingateGroup) -> GroupMapping:
    return GroupMapping(
        from_group=from_group,
        to_group=to_group,
        confidence=0.9,
        is_confirmed=True,
    )


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------

def test_empty_mappings_returns_empty_plan() -> None:
    resources = [_resource("r1", "prod-db", [_edge("f1")])]
    plan = build_plan([], resources)
    assert plan.actions == []


def test_unconfirmed_mapping_excluded() -> None:
    """Mappings with is_confirmed=False are not included in the plan."""
    f1 = _group("f1", "Okta-Eng")
    t1 = _group("t1", "Entra-Eng")
    mapping = GroupMapping(from_group=f1, to_group=t1, confidence=0.9, is_confirmed=False)
    resources = [_resource("r1", "prod-db", [_edge("f1")])]
    plan = build_plan([mapping], resources)
    assert plan.actions == []


def test_mapping_without_to_group_excluded() -> None:
    """Confirmed mappings with no to_group are not included."""
    f1 = _group("f1", "Okta-Eng")
    mapping = GroupMapping(from_group=f1, to_group=None, confidence=0.0, is_confirmed=True)
    resources = [_resource("r1", "prod-db", [_edge("f1")])]
    plan = build_plan([mapping], resources)
    assert plan.actions == []


def test_basic_action_created() -> None:
    """One confirmed mapping + one resource = one action."""
    f1 = _group("f1", "Okta-Eng")
    t1 = _group("t1", "Entra-Eng")
    resource = _resource("r1", "prod-db", [_edge("f1", "pol-1", "MFA Required")])
    plan = build_plan([_confirmed_mapping(f1, t1)], [resource])

    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.resource_id == "r1"
    assert action.resource_name == "prod-db"
    assert action.from_group_id == "f1"
    assert action.to_group_id == "t1"
    assert action.security_policy_id == "pol-1"
    assert action.security_policy_name == "MFA Required"
    assert action.access_policy_mode == AccessPolicyMode.MANUAL


def test_from_group_not_on_resource_skipped() -> None:
    """Resource without from_group access produces no action."""
    f1 = _group("f1", "Okta-Eng")
    t1 = _group("t1", "Entra-Eng")
    resource = _resource("r1", "prod-db", [_edge("other-group")])
    plan = build_plan([_confirmed_mapping(f1, t1)], [resource])
    assert plan.actions == []


def test_to_group_already_has_access_skipped() -> None:
    """If to_group already has access, no duplicate action is created."""
    f1 = _group("f1", "Okta-Eng")
    t1 = _group("t1", "Entra-Eng")
    # Both f1 and t1 already have access
    resource = _resource("r1", "prod-db", [_edge("f1"), _edge("t1")])
    plan = build_plan([_confirmed_mapping(f1, t1)], [resource])
    assert plan.actions == []


def test_multiple_resources_multiple_actions() -> None:
    """One mapping across multiple resources creates one action per resource."""
    f1 = _group("f1", "Okta-Eng")
    t1 = _group("t1", "Entra-Eng")
    r1 = _resource("r1", "prod-db", [_edge("f1")])
    r2 = _resource("r2", "staging-api", [_edge("f1")])
    r3 = _resource("r3", "dev-tools", [_edge("other")])  # f1 not on this
    plan = build_plan([_confirmed_mapping(f1, t1)], [r1, r2, r3])
    assert len(plan.actions) == 2
    resource_ids = {a.resource_id for a in plan.actions}
    assert resource_ids == {"r1", "r2"}


def test_multiple_mappings_combined() -> None:
    """Two confirmed mappings across shared resources produce correct actions."""
    f1, t1 = _group("f1", "Okta-Eng"), _group("t1", "Entra-Eng")
    f2, t2 = _group("f2", "Okta-Finance"), _group("t2", "Entra-Finance")
    r1 = _resource("r1", "prod-db", [_edge("f1"), _edge("f2")])
    r2 = _resource("r2", "finance-app", [_edge("f2")])
    plan = build_plan(
        [_confirmed_mapping(f1, t1), _confirmed_mapping(f2, t2)],
        [r1, r2],
    )
    assert len(plan.actions) == 3  # t1->r1, t2->r1, t2->r2


def test_action_preserves_access_policy_mode() -> None:
    """The from_group's access policy mode is copied to the action."""
    f1, t1 = _group("f1", "Okta-Eng"), _group("t1", "Entra-Eng")
    resource = _resource("r1", "prod", [_edge("f1", mode=AccessPolicyMode.AUTO_LOCK)])
    plan = build_plan([_confirmed_mapping(f1, t1)], [resource])
    assert plan.actions[0].access_policy_mode == AccessPolicyMode.AUTO_LOCK


def test_action_no_security_policy_when_edge_has_none() -> None:
    """Actions with no security policy produce None for policy fields."""
    f1, t1 = _group("f1", "Okta-Eng"), _group("t1", "Entra-Eng")
    edge = AccessEdge(principal_id="f1")  # no security_policy
    resource = _resource("r1", "prod", [edge])
    plan = build_plan([_confirmed_mapping(f1, t1)], [resource])
    assert plan.actions[0].security_policy_id is None
    assert plan.actions[0].security_policy_name is None


def test_plan_stores_original_mappings() -> None:
    """The returned MigrationPlan includes the original mappings list."""
    f1, t1 = _group("f1", "Okta-Eng"), _group("t1", "Entra-Eng")
    mapping = _confirmed_mapping(f1, t1)
    plan = build_plan([mapping], [])
    assert plan.mappings == [mapping]
