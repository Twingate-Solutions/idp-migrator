"""Pydantic v2 data models for twingate-idp-migrator."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class GroupType(StrEnum):
    """Twingate group type."""

    MANUAL = "MANUAL"
    SYNCED = "SYNCED"
    SYSTEM = "SYSTEM"


class AccessPolicyMode(StrEnum):
    """Access policy mode for a resource access edge."""

    MANUAL = "MANUAL"
    AUTO_LOCK = "AUTO_LOCK"
    ACCESS_REQUEST = "ACCESS_REQUEST"


class SecurityPolicyRef(BaseModel):
    """Reference to a Twingate security policy."""

    id: str
    name: str


class AccessPolicy(BaseModel):
    """Access policy applied to a resource access edge."""

    mode: AccessPolicyMode


class TwingateGroup(BaseModel):
    """A Twingate group (MANUAL, SYNCED, or SYSTEM)."""

    id: str
    name: str
    type: GroupType
    origin_id: str | None = None
    is_active: bool = True
    security_policy: SecurityPolicyRef | None = None


class AccessEdge(BaseModel):
    """One group's access to one resource with its policy settings."""

    principal_id: str
    security_policy: SecurityPolicyRef | None = None
    expires_at: datetime | None = None
    access_policy: AccessPolicy | None = None


class TwingateResource(BaseModel):
    """A Twingate resource with its current access edges."""

    id: str
    name: str
    address: str | None = None
    is_active: bool = True
    access_edges: list[AccessEdge] = Field(default_factory=list)


class GroupMapping(BaseModel):
    """A single from→to group mapping with fuzzy match metadata."""

    from_group: TwingateGroup
    to_group: TwingateGroup | None = None
    confidence: float = 0.0  # 0.0–1.0
    is_confirmed: bool = False


class MigrationAction(BaseModel):
    """A single planned API call: add to_group to resource with from_group's settings."""

    resource_id: str
    resource_name: str
    from_group_id: str
    from_group_name: str
    to_group_id: str
    to_group_name: str
    security_policy_id: str | None = None
    security_policy_name: str | None = None
    expires_at: datetime | None = None
    access_policy_mode: AccessPolicyMode | None = None


class MigrationPlan(BaseModel):
    """The complete set of actions to execute for a migration."""

    actions: list[MigrationAction] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    mappings: list[GroupMapping] = Field(default_factory=list)


class ChangeLogEntry(BaseModel):
    """One executed mutation, saved for rollback."""

    action: MigrationAction
    executed_at: datetime
    success: bool
    error: str | None = None


class ChangeLog(BaseModel):
    """The full changelog from one migration run."""

    tenant: str
    started_at: datetime
    completed_at: datetime | None = None
    entries: list[ChangeLogEntry] = Field(default_factory=list)
