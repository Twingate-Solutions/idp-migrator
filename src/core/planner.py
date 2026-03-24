"""Migration plan builder for twingate-idp-migrator.

Reads current resource access data and confirmed group mappings to produce
a MigrationPlan describing every resourceAccessAdd call needed.
"""

from __future__ import annotations

from src.models import (
    GroupMapping,
    MigrationAction,
    MigrationPlan,
    TwingateResource,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


def build_plan(
    mappings: list[GroupMapping],
    resources: list[TwingateResource],
) -> MigrationPlan:
    """Build a MigrationPlan from confirmed group mappings and resource data.

    For each confirmed mapping (from_group -> to_group), finds every resource
    where from_group currently has access, then creates a MigrationAction for
    each resource where to_group does NOT already have access. Skips
    resources where to_group already has access (idempotent).

    Args:
        mappings: All group mappings (confirmed and unconfirmed).
        resources: All Twingate resources with their current access edges.

    Returns:
        A MigrationPlan with all required actions.
    """
    confirmed = [m for m in mappings if m.is_confirmed and m.to_group is not None]

    if not confirmed:
        logger.info("build_plan_no_confirmed_mappings")
        return MigrationPlan(mappings=mappings)

    actions: list[MigrationAction] = []

    for mapping in confirmed:
        to_group = mapping.to_group  # already verified not None above
        assert to_group is not None  # narrow type for mypy

        for resource in resources:
            # Find the from_group's access edge on this resource (if any)
            from_edge = next(
                (e for e in resource.access_edges if e.principal_id == mapping.from_group.id),
                None,
            )
            if from_edge is None:
                # from_group does not have access to this resource — skip
                continue

            # Check if to_group already has access (idempotent skip)
            already_has_access = any(
                e.principal_id == to_group.id for e in resource.access_edges
            )
            if already_has_access:
                logger.debug(
                    "plan_skip_already_has_access",
                    resource_id=resource.id,
                    to_group_id=to_group.id,
                )
                continue

            actions.append(
                MigrationAction(
                    resource_id=resource.id,
                    resource_name=resource.name,
                    from_group_id=mapping.from_group.id,
                    from_group_name=mapping.from_group.name,
                    to_group_id=to_group.id,
                    to_group_name=to_group.name,
                    security_policy_id=from_edge.security_policy.id
                    if from_edge.security_policy
                    else None,
                    security_policy_name=from_edge.security_policy.name
                    if from_edge.security_policy
                    else None,
                    expires_at=from_edge.expires_at,
                    access_policy_mode=from_edge.access_policy.mode
                    if from_edge.access_policy
                    else None,
                    access_policy_duration_seconds=from_edge.access_policy.duration_seconds
                    if from_edge.access_policy
                    else None,
                )
            )

    logger.info(
        "build_plan_complete",
        confirmed_mappings=len(confirmed),
        actions=len(actions),
    )
    return MigrationPlan(actions=actions, mappings=mappings)
