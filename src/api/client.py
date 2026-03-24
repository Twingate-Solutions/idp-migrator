"""Twingate GraphQL API client with async httpx, pagination, and rate limiting."""

from __future__ import annotations

import asyncio
import contextlib
import random
from typing import Any

import httpx

from src.api.mutations import RESOURCE_ACCESS_ADD, RESOURCE_ACCESS_REMOVE
from src.api.queries import GET_RESOURCE_ACCESS, LIST_GROUPS, LIST_RESOURCES
from src.models import (
    AccessEdge,
    AccessPolicy,
    AccessPolicyMode,
    GroupType,
    SecurityPolicyRef,
    TwingateGroup,
    TwingateResource,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

_PAGE_SIZE = 50
_BASE_BACKOFF = 1.0
_MAX_BACKOFF = 60.0
_BACKOFF_FACTOR = 2.0
_MAX_RETRIES = 5


class TwingateAPIError(Exception):
    """Raised when the Twingate API returns a GraphQL-level error."""


class TwingateAuthError(TwingateAPIError):
    """Raised when the API key is invalid or lacks required scope."""


class AccessInput:
    """Input for a single access entry in resourceAccessAdd."""

    __slots__ = (
        "principal_id",
        "security_policy_id",
        "expires_at",
        "access_policy_mode",
        "access_policy_duration_seconds",
    )

    def __init__(
        self,
        principal_id: str,
        security_policy_id: str | None = None,
        expires_at: str | None = None,
        access_policy_mode: AccessPolicyMode | None = None,
        access_policy_duration_seconds: int | None = None,
    ) -> None:
        """Initialise an access input entry.

        Args:
            principal_id: The group ID to grant access to.
            security_policy_id: Optional security policy override.
            expires_at: ISO-8601 timestamp for ephemeral access, or None.
            access_policy_mode: Access mode override, or None for default.
            access_policy_duration_seconds: Required when mode is AUTO_LOCK.
        """
        self.principal_id = principal_id
        self.security_policy_id = security_policy_id
        self.expires_at = expires_at
        self.access_policy_mode = access_policy_mode
        self.access_policy_duration_seconds = access_policy_duration_seconds

    def to_graphql_dict(self) -> dict[str, Any]:
        """Serialise to a dict suitable for GraphQL variables."""
        result: dict[str, Any] = {"principalId": self.principal_id}
        if self.security_policy_id is not None:
            result["securityPolicyId"] = self.security_policy_id
        if self.expires_at is not None:
            result["expiresAt"] = self.expires_at
        if self.access_policy_mode is not None:
            ap: dict[str, Any] = {"mode": str(self.access_policy_mode)}
            if self.access_policy_duration_seconds is not None:
                ap["durationSeconds"] = self.access_policy_duration_seconds
            result["accessPolicy"] = ap
        return result


class TwingateClient:
    """Async client for the Twingate Admin GraphQL API.

    All public methods are coroutines. The client must be used as an async
    context manager or closed explicitly via ``close()``.

    Example::

        async with TwingateClient("acme", "api-key") as client:
            ok = await client.connect()
            groups = await client.fetch_all_groups()
    """

    def __init__(self, tenant: str, api_key: str) -> None:
        """Initialise the client.

        Args:
            tenant: Twingate tenant name (e.g. "acme" for acme.twingate.com).
            api_key: Admin API key. Never logged or persisted.
        """
        self._tenant = tenant
        self._url = f"https://{tenant}.twingate.com/api/graphql/"
        # api_key intentionally not stored as a public attribute
        self._headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        }
        self._closed: bool = False
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> TwingateClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    def _make_http_client(self) -> httpx.AsyncClient:
        """Create a new HTTP client bound to the current event loop."""
        return httpx.AsyncClient(
            headers=self._headers,
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=5.0),
        )

    async def _close_http(self) -> None:
        """Close and discard the HTTP client without permanently closing this instance.

        Call this at the end of each asyncio.run() invocation so the next
        call gets a fresh client bound to its own event loop.
        """
        if self._http is not None:
            with contextlib.suppress(Exception):
                await self._http.aclose()
            self._http = None

    async def close(self) -> None:
        """Permanently close the underlying HTTP client."""
        self._closed = True
        await self._close_http()

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    async def _post(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute one GraphQL request with retry/backoff on 429 and 5xx.

        Args:
            query: GraphQL query or mutation string.
            variables: Optional variables dict.

        Returns:
            Parsed JSON response body.

        Raises:
            TwingateAuthError: On HTTP 401/403.
            TwingateAPIError: On unrecoverable HTTP errors or GraphQL errors.
        """
        if self._closed:
            raise TwingateAPIError("Client is already closed")

        if self._http is None:
            self._http = self._make_http_client()

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        backoff = _BASE_BACKOFF
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await self._http.post(self._url, json=payload)
            except httpx.TransportError as exc:
                logger.warning(
                    "graphql_transport_error",
                    attempt=attempt,
                    error=str(exc),
                    tenant=self._tenant,
                )
                if attempt == _MAX_RETRIES:
                    msg = f"Transport error after {attempt} attempts: {exc}"
                    raise TwingateAPIError(msg) from exc
                await self._sleep_backoff(backoff)
                backoff = min(backoff * _BACKOFF_FACTOR, _MAX_BACKOFF)
                continue

            if resp.status_code in (401, 403):
                raise TwingateAuthError(
                    f"Authentication failed (HTTP {resp.status_code}). "
                    "Check that the API key is valid and has read+write scope."
                )

            if resp.status_code == 429:
                logger.warning(
                    "graphql_rate_limited",
                    attempt=attempt,
                    backoff_seconds=backoff,
                    tenant=self._tenant,
                )
                if attempt == _MAX_RETRIES:
                    raise TwingateAPIError(
                        f"Rate limited by Twingate API after {attempt} attempts"
                    )
                await self._sleep_backoff(backoff)
                backoff = min(backoff * _BACKOFF_FACTOR, _MAX_BACKOFF)
                continue

            if resp.status_code >= 500:
                logger.warning(
                    "graphql_server_error",
                    status_code=resp.status_code,
                    attempt=attempt,
                    response_preview=resp.text[:200],
                    tenant=self._tenant,
                )
                if attempt == _MAX_RETRIES:
                    raise TwingateAPIError(
                        f"Server error {resp.status_code} after {attempt} attempts"
                    )
                await self._sleep_backoff(backoff)
                backoff = min(backoff * _BACKOFF_FACTOR, _MAX_BACKOFF)
                continue

            if resp.status_code != 200:
                raise TwingateAPIError(f"Unexpected HTTP {resp.status_code}: {resp.text[:200]}")

            body: dict[str, Any] = resp.json()
            if "errors" in body:
                errors = body["errors"]
                logger.error(
                    "graphql_errors",
                    errors=errors,
                    tenant=self._tenant,
                )
                raise TwingateAPIError(f"GraphQL errors: {errors}")

            return body

        # Should never reach here
        raise TwingateAPIError("Max retries exceeded")

    @staticmethod
    async def _sleep_backoff(seconds: float) -> None:
        """Sleep with full jitter: uniform random between 0 and ``seconds``."""
        await asyncio.sleep(random.uniform(0, seconds))  # noqa: S311

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Test connectivity by fetching a single group page.

        Returns:
            True if the tenant is reachable and the API key is valid.

        Raises:
            TwingateAuthError: If the API key is invalid.
            TwingateAPIError: If the tenant is unreachable.
        """
        await self._post(LIST_GROUPS, {"first": 1})
        logger.info("twingate_connected", tenant=self._tenant)
        return True

    async def fetch_all_groups(
        self, type_filter: list[GroupType] | None = None
    ) -> list[TwingateGroup]:
        """Fetch all groups, paginating to completion.

        Args:
            type_filter: If provided, only return groups of these types.
                         Defaults to all types if None.

        Returns:
            All matching groups across all pages.
        """
        groups: list[TwingateGroup] = []
        cursor: str | None = None

        filter_val: dict[str, Any] | None = None
        if type_filter:
            filter_val = {"type": {"in": [str(t) for t in type_filter]}}

        while True:
            variables: dict[str, Any] = {"first": _PAGE_SIZE}
            if filter_val:
                variables["filter"] = filter_val
            if cursor:
                variables["after"] = cursor
            body = await self._post(LIST_GROUPS, variables)
            page = body["data"]["groups"]

            for edge in page["edges"]:
                node = edge["node"]
                sp_node = node.get("securityPolicy")
                groups.append(
                    TwingateGroup(
                        id=node["id"],
                        name=node["name"],
                        type=GroupType(node["type"]),
                        origin_id=node.get("originId"),
                        is_active=node.get("isActive", True),
                        security_policy=SecurityPolicyRef(
                            id=sp_node["id"], name=sp_node["name"]
                        )
                        if sp_node
                        else None,
                    )
                )

            page_info = page["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            cursor = page_info["endCursor"]

        logger.info(
            "groups_fetched",
            count=len(groups),
            type_filter=[str(t) for t in type_filter] if type_filter else None,
            tenant=self._tenant,
        )
        return groups

    async def fetch_all_resources_with_access(self) -> list[TwingateResource]:
        """Fetch all resources including their access edges, paginating both levels.

        Returns:
            All resources with populated ``access_edges``.
        """
        resources: list[TwingateResource] = []
        cursor: str | None = None

        while True:
            variables: dict[str, Any] = {"first": _PAGE_SIZE}
            if cursor:
                variables["after"] = cursor

            body = await self._post(LIST_RESOURCES, variables)
            page = body["data"]["resources"]

            for edge in page["edges"]:
                node = edge["node"]
                addr_node = node.get("address") or {}
                access_edges = _parse_access_edges(node["access"]["edges"])

                # If the nested access page has more results, fetch them
                access_page_info = node["access"]["pageInfo"]
                if access_page_info["hasNextPage"]:
                    extra = await self.fetch_resource_access(
                        node["id"], after=access_page_info["endCursor"]
                    )
                    access_edges.extend(extra)

                resources.append(
                    TwingateResource(
                        id=node["id"],
                        name=node["name"],
                        address=addr_node.get("value"),
                        is_active=node.get("isActive", True),
                        access_edges=access_edges,
                    )
                )

            page_info = page["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            cursor = page_info["endCursor"]

        logger.info("resources_fetched", count=len(resources), tenant=self._tenant)
        return resources

    async def fetch_resource_access(
        self, resource_id: str, after: str | None = None
    ) -> list[AccessEdge]:
        """Fetch access edges for a single resource, paginating to completion.

        Args:
            resource_id: Twingate resource ID.
            after: Optional cursor to start from (for continuation).

        Returns:
            All access edges for the resource.
        """
        edges: list[AccessEdge] = []
        cursor: str | None = after

        while True:
            variables: dict[str, Any] = {"id": resource_id, "first": _PAGE_SIZE}
            if cursor:
                variables["after"] = cursor

            body = await self._post(GET_RESOURCE_ACCESS, variables)
            access_page = body["data"]["resource"]["access"]
            edges.extend(_parse_access_edges(access_page["edges"]))

            if not access_page["pageInfo"]["hasNextPage"]:
                break
            cursor = access_page["pageInfo"]["endCursor"]

        return edges

    async def add_resource_access(
        self, resource_id: str, access: list[AccessInput]
    ) -> bool:
        """Add one or more group access entries to a resource.

        Args:
            resource_id: Twingate resource ID.
            access: List of AccessInput entries to add.

        Returns:
            True if the API reported success.

        Raises:
            TwingateAPIError: On transport or server errors.
        """
        variables: dict[str, Any] = {
            "resourceId": resource_id,
            "access": [a.to_graphql_dict() for a in access],
        }
        body = await self._post(RESOURCE_ACCESS_ADD, variables)
        result = body["data"]["resourceAccessAdd"]
        if not result["ok"]:
            logger.error(
                "resource_access_add_failed",
                resource_id=resource_id,
                error=result.get("error"),
                tenant=self._tenant,
            )
        return bool(result["ok"])

    async def remove_resource_access(
        self, resource_id: str, principal_ids: list[str]
    ) -> bool:
        """Remove group access entries from a resource (used for rollback).

        Args:
            resource_id: Twingate resource ID.
            principal_ids: List of group IDs to remove.

        Returns:
            True if the API reported success.

        Raises:
            TwingateAPIError: On transport or server errors.
        """
        variables: dict[str, Any] = {
            "resourceId": resource_id,
            "principalIds": principal_ids,
        }
        body = await self._post(RESOURCE_ACCESS_REMOVE, variables)
        result = body["data"]["resourceAccessRemove"]
        if not result["ok"]:
            logger.error(
                "resource_access_remove_failed",
                resource_id=resource_id,
                error=result.get("error"),
                tenant=self._tenant,
            )
        return bool(result["ok"])


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _parse_access_edges(raw_edges: list[dict[str, Any]]) -> list[AccessEdge]:
    """Parse a list of raw GraphQL access edge nodes into AccessEdge models.

    Args:
        raw_edges: List of ``{"node": {...}}`` dicts from a GraphQL response.

    Returns:
        Parsed list of AccessEdge instances.
    """
    result: list[AccessEdge] = []
    for edge in raw_edges:
        node = edge["node"]
        sp_node = edge.get("securityPolicy")
        ap_node = edge.get("accessPolicy")
        result.append(
            AccessEdge(
                principal_id=node["id"],
                security_policy=SecurityPolicyRef(id=sp_node["id"], name=sp_node["name"])
                if sp_node
                else None,
                expires_at=edge.get("expiresAt"),
                access_policy=AccessPolicy(
                    mode=AccessPolicyMode(ap_node["mode"]),
                    duration_seconds=ap_node.get("durationSeconds"),
                )
                if ap_node
                else None,
            )
        )
    return result
