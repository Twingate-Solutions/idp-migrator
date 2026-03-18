"""Shared pytest fixtures for twingate-idp-migrator tests."""

from typing import Any

import pytest

from src.models import (
    AccessEdge,
    AccessPolicy,
    AccessPolicyMode,
    GroupType,
    SecurityPolicyRef,
    TwingateGroup,
    TwingateResource,
)


@pytest.fixture
def synced_group() -> TwingateGroup:
    """A typical SYNCED group from a new IdP."""
    return TwingateGroup(
        id="R3JvdXA6MjAw",
        name="Entra-Engineering",
        type=GroupType.SYNCED,
        origin_id="ext-456",
        is_active=True,
    )


@pytest.fixture
def old_synced_group() -> TwingateGroup:
    """A typical SYNCED group from an old IdP."""
    return TwingateGroup(
        id="R3JvdXA6MTAw",
        name="Okta-Engineering",
        type=GroupType.SYNCED,
        origin_id="ext-123",
        is_active=True,
    )


@pytest.fixture
def resource_with_access(old_synced_group: TwingateGroup) -> TwingateResource:
    """A resource with one existing access edge for old_synced_group."""
    return TwingateResource(
        id="UmVzb3VyY2U6MQ",
        name="prod-db.internal",
        address="10.0.0.1",
        is_active=True,
        access_edges=[
            AccessEdge(
                principal_id=old_synced_group.id,
                security_policy=SecurityPolicyRef(
                    id="U2VjdXJpdHlQb2xpY3k6MQ", name="MFA Required"
                ),
                expires_at=None,
                access_policy=AccessPolicy(mode=AccessPolicyMode.MANUAL),
            )
        ],
    )


def _make_groups_page(
    groups: list[dict[str, Any]],
    has_next: bool = False,
    end_cursor: str | None = None,
) -> dict[str, Any]:
    """Build a groups GraphQL response page."""
    return {
        "data": {
            "groups": {
                "pageInfo": {
                    "hasNextPage": has_next,
                    "endCursor": end_cursor,
                },
                "edges": [{"node": g} for g in groups],
                "totalCount": len(groups),
            }
        }
    }


def _make_resources_page(
    resources: list[dict[str, Any]],
    has_next: bool = False,
    end_cursor: str | None = None,
) -> dict[str, Any]:
    """Build a resources GraphQL response page."""
    return {
        "data": {
            "resources": {
                "pageInfo": {
                    "hasNextPage": has_next,
                    "endCursor": end_cursor,
                },
                "edges": [{"node": r} for r in resources],
                "totalCount": len(resources),
            }
        }
    }
