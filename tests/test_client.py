"""Comprehensive tests for the Twingate GraphQL API client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_httpx import HTTPXMock

from src.api.client import (
    AccessInput,
    TwingateAPIError,
    TwingateAuthError,
    TwingateClient,
)
from src.models import AccessPolicyMode, GroupType
from tests.conftest import _make_groups_page, _make_resources_page

TENANT = "test-tenant"
API_KEY = "tg-test-api-key-000"
GQL_URL = f"https://{TENANT}.twingate.com/api/graphql/"

_GROUP_NODE: dict[str, Any] = {
    "id": "R3JvdXA6MTAw",
    "name": "Okta-Engineering",
    "type": "SYNCED",
    "originId": "ext-123",
    "isActive": True,
    "securityPolicy": {"id": "U2VjdXJpdHlQb2xpY3k6MQ", "name": "MFA Required"},
}

_GROUP_NODE_NO_SP: dict[str, Any] = {
    "id": "R3JvdXA6MjAw",
    "name": "Manual-Team",
    "type": "MANUAL",
    "originId": None,
    "isActive": True,
    "securityPolicy": None,
}

_RESOURCE_NODE: dict[str, Any] = {
    "id": "UmVzb3VyY2U6MQ",
    "name": "prod-db.internal",
    "address": {"value": "10.0.0.1"},
    "isActive": True,
    "access": {
        "edges": [
            {
                "node": {"id": "R3JvdXA6MTAw"},
                "securityPolicy": {
                    "id": "U2VjdXJpdHlQb2xpY3k6MQ",
                    "name": "MFA Required",
                },
                "expiresAt": None,
                "accessPolicy": {"mode": "MANUAL", "durationSeconds": None},
            }
        ],
        "pageInfo": {"hasNextPage": False, "endCursor": None},
    },
}


# ------------------------------------------------------------------
# connect() tests
# ------------------------------------------------------------------


class TestConnect:
    """Tests for TwingateClient.connect()."""

    async def test_connect_success(self, httpx_mock: HTTPXMock) -> None:
        """Successful connect returns True on 200 with valid data."""
        httpx_mock.add_response(
            url=GQL_URL,
            json=_make_groups_page([_GROUP_NODE]),
        )
        async with TwingateClient(TENANT, API_KEY) as client:
            result = await client.connect()
        assert result is True

    async def test_connect_auth_failure_401(self, httpx_mock: HTTPXMock) -> None:
        """HTTP 401 raises TwingateAuthError."""
        httpx_mock.add_response(url=GQL_URL, status_code=401)
        async with TwingateClient(TENANT, API_KEY) as client:
            with pytest.raises(TwingateAuthError, match="Authentication failed"):
                await client.connect()

    async def test_connect_auth_failure_403(self, httpx_mock: HTTPXMock) -> None:
        """HTTP 403 raises TwingateAuthError."""
        httpx_mock.add_response(url=GQL_URL, status_code=403)
        async with TwingateClient(TENANT, API_KEY) as client:
            with pytest.raises(TwingateAuthError, match="Authentication failed"):
                await client.connect()


# ------------------------------------------------------------------
# fetch_all_groups() tests
# ------------------------------------------------------------------


class TestFetchAllGroups:
    """Tests for TwingateClient.fetch_all_groups()."""

    async def test_single_page(self, httpx_mock: HTTPXMock) -> None:
        """Single page of groups returns all groups correctly parsed."""
        httpx_mock.add_response(
            url=GQL_URL,
            json=_make_groups_page([_GROUP_NODE]),
        )
        async with TwingateClient(TENANT, API_KEY) as client:
            groups = await client.fetch_all_groups()

        assert len(groups) == 1
        g = groups[0]
        assert g.id == "R3JvdXA6MTAw"
        assert g.name == "Okta-Engineering"
        assert g.type == GroupType.SYNCED
        assert g.origin_id == "ext-123"
        assert g.is_active is True
        assert g.security_policy is not None
        assert g.security_policy.id == "U2VjdXJpdHlQb2xpY3k6MQ"
        assert g.security_policy.name == "MFA Required"

    async def test_multi_page_pagination(self, httpx_mock: HTTPXMock) -> None:
        """Groups spanning two pages are all collected."""
        page1 = _make_groups_page(
            [_GROUP_NODE], has_next=True, end_cursor="cursor-1"
        )
        page2 = _make_groups_page([_GROUP_NODE_NO_SP])
        httpx_mock.add_response(url=GQL_URL, json=page1)
        httpx_mock.add_response(url=GQL_URL, json=page2)

        async with TwingateClient(TENANT, API_KEY) as client:
            groups = await client.fetch_all_groups()

        assert len(groups) == 2
        assert groups[0].name == "Okta-Engineering"
        assert groups[1].name == "Manual-Team"

    async def test_type_filter_passed_through(self, httpx_mock: HTTPXMock) -> None:
        """type_filter is sent as a GraphQL filter variable."""
        httpx_mock.add_response(
            url=GQL_URL,
            json=_make_groups_page([_GROUP_NODE]),
        )
        async with TwingateClient(TENANT, API_KEY) as client:
            await client.fetch_all_groups(type_filter=[GroupType.SYNCED])

        request = httpx_mock.get_request()
        assert request is not None
        body = request.read()
        import json

        payload = json.loads(body)
        assert payload["variables"]["filter"] == {"type": {"in": ["SYNCED"]}}

    async def test_group_with_no_security_policy(self, httpx_mock: HTTPXMock) -> None:
        """Groups without a securityPolicy parse correctly with None."""
        httpx_mock.add_response(
            url=GQL_URL,
            json=_make_groups_page([_GROUP_NODE_NO_SP]),
        )
        async with TwingateClient(TENANT, API_KEY) as client:
            groups = await client.fetch_all_groups()

        assert len(groups) == 1
        assert groups[0].security_policy is None
        assert groups[0].type == GroupType.MANUAL


# ------------------------------------------------------------------
# fetch_all_resources_with_access() tests
# ------------------------------------------------------------------


class TestFetchAllResourcesWithAccess:
    """Tests for TwingateClient.fetch_all_resources_with_access()."""

    async def test_single_page(self, httpx_mock: HTTPXMock) -> None:
        """Single page of resources parses correctly with access edges."""
        httpx_mock.add_response(
            url=GQL_URL,
            json=_make_resources_page([_RESOURCE_NODE]),
        )
        async with TwingateClient(TENANT, API_KEY) as client:
            resources = await client.fetch_all_resources_with_access()

        assert len(resources) == 1
        r = resources[0]
        assert r.id == "UmVzb3VyY2U6MQ"
        assert r.name == "prod-db.internal"
        assert r.address == "10.0.0.1"
        assert r.is_active is True
        assert len(r.access_edges) == 1
        edge = r.access_edges[0]
        assert edge.principal_id == "R3JvdXA6MTAw"
        assert edge.security_policy is not None
        assert edge.security_policy.id == "U2VjdXJpdHlQb2xpY3k6MQ"
        assert edge.access_policy is not None
        assert edge.access_policy.mode == AccessPolicyMode.MANUAL

    async def test_multi_page_pagination(self, httpx_mock: HTTPXMock) -> None:
        """Resources spanning two pages are all collected."""
        resource2: dict[str, Any] = {
            "id": "UmVzb3VyY2U6Mg",
            "name": "staging-app.internal",
            "address": {"value": "10.0.0.2"},
            "isActive": True,
            "access": {
                "edges": [],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
        }
        page1 = _make_resources_page(
            [_RESOURCE_NODE], has_next=True, end_cursor="res-cursor-1"
        )
        page2 = _make_resources_page([resource2])
        httpx_mock.add_response(url=GQL_URL, json=page1)
        httpx_mock.add_response(url=GQL_URL, json=page2)

        async with TwingateClient(TENANT, API_KEY) as client:
            resources = await client.fetch_all_resources_with_access()

        assert len(resources) == 2
        assert resources[0].name == "prod-db.internal"
        assert resources[1].name == "staging-app.internal"
        assert len(resources[1].access_edges) == 0

    async def test_nested_access_pagination(self, httpx_mock: HTTPXMock) -> None:
        """When nested access has hasNextPage=True, extra edges are fetched."""
        resource_with_paged_access: dict[str, Any] = {
            "id": "UmVzb3VyY2U6MQ",
            "name": "prod-db.internal",
            "address": {"value": "10.0.0.1"},
            "isActive": True,
            "access": {
                "edges": [
                    {
                        "node": {"id": "R3JvdXA6MTAw"},
                        "securityPolicy": None,
                        "expiresAt": None,
                        "accessPolicy": None,
                    }
                ],
                "pageInfo": {
                    "hasNextPage": True,
                    "endCursor": "access-cursor-1",
                },
            },
        }
        # First response: resource list page
        httpx_mock.add_response(
            url=GQL_URL,
            json=_make_resources_page([resource_with_paged_access]),
        )
        # Second response: fetch_resource_access continuation
        httpx_mock.add_response(
            url=GQL_URL,
            json={
                "data": {
                    "resource": {
                        "access": {
                            "edges": [
                                {
                                    "node": {"id": "R3JvdXA6MjAw"},
                                    "securityPolicy": None,
                                    "expiresAt": None,
                                    "accessPolicy": {"mode": "AUTO_LOCK", "durationSeconds": 86400},
                                }
                            ],
                            "pageInfo": {
                                "hasNextPage": False,
                                "endCursor": None,
                            },
                        }
                    }
                }
            },
        )

        async with TwingateClient(TENANT, API_KEY) as client:
            resources = await client.fetch_all_resources_with_access()

        assert len(resources) == 1
        assert len(resources[0].access_edges) == 2
        assert resources[0].access_edges[0].principal_id == "R3JvdXA6MTAw"
        assert resources[0].access_edges[1].principal_id == "R3JvdXA6MjAw"
        assert resources[0].access_edges[1].access_policy is not None
        assert resources[0].access_edges[1].access_policy.mode == AccessPolicyMode.AUTO_LOCK
        assert resources[0].access_edges[1].access_policy.duration_seconds == 86400


# ------------------------------------------------------------------
# add_resource_access() tests
# ------------------------------------------------------------------


class TestAddResourceAccess:
    """Tests for TwingateClient.add_resource_access()."""

    async def test_success(self, httpx_mock: HTTPXMock) -> None:
        """Returns True when API reports ok=True."""
        httpx_mock.add_response(
            url=GQL_URL,
            json={
                "data": {
                    "resourceAccessAdd": {
                        "ok": True,
                        "error": None,
                        "entity": {"id": "UmVzb3VyY2U6MQ", "name": "prod-db"},
                    }
                }
            },
        )
        access_input = AccessInput(
            principal_id="R3JvdXA6MjAw",
            security_policy_id="U2VjdXJpdHlQb2xpY3k6MQ",
        )
        async with TwingateClient(TENANT, API_KEY) as client:
            result = await client.add_resource_access("UmVzb3VyY2U6MQ", [access_input])
        assert result is True

    async def test_failure(self, httpx_mock: HTTPXMock) -> None:
        """Returns False when API reports ok=False."""
        httpx_mock.add_response(
            url=GQL_URL,
            json={
                "data": {
                    "resourceAccessAdd": {
                        "ok": False,
                        "error": "Resource not found",
                        "entity": None,
                    }
                }
            },
        )
        access_input = AccessInput(principal_id="R3JvdXA6MjAw")
        async with TwingateClient(TENANT, API_KEY) as client:
            result = await client.add_resource_access("bad-id", [access_input])
        assert result is False


# ------------------------------------------------------------------
# remove_resource_access() tests
# ------------------------------------------------------------------


class TestRemoveResourceAccess:
    """Tests for TwingateClient.remove_resource_access()."""

    async def test_success(self, httpx_mock: HTTPXMock) -> None:
        """Returns True when API reports ok=True."""
        httpx_mock.add_response(
            url=GQL_URL,
            json={
                "data": {
                    "resourceAccessRemove": {
                        "ok": True,
                        "error": None,
                        "entity": {"id": "UmVzb3VyY2U6MQ", "name": "prod-db"},
                    }
                }
            },
        )
        async with TwingateClient(TENANT, API_KEY) as client:
            result = await client.remove_resource_access(
                "UmVzb3VyY2U6MQ", ["R3JvdXA6MTAw"]
            )
        assert result is True


# ------------------------------------------------------------------
# Error handling tests
# ------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling in _post()."""

    async def test_graphql_errors_raises(self, httpx_mock: HTTPXMock) -> None:
        """A response with 'errors' key raises TwingateAPIError."""
        httpx_mock.add_response(
            url=GQL_URL,
            json={
                "errors": [{"message": "Field 'bad' not found"}],
                "data": None,
            },
        )
        async with TwingateClient(TENANT, API_KEY) as client:
            with pytest.raises(TwingateAPIError, match="GraphQL errors"):
                await client.connect()

    @patch.object(TwingateClient, "_sleep_backoff", new=AsyncMock())
    async def test_5xx_retries_then_raises(self, httpx_mock: HTTPXMock) -> None:
        """5xx responses are retried up to max retries, then raise."""
        for _ in range(5):
            httpx_mock.add_response(url=GQL_URL, status_code=500, text="Internal Server Error")

        async with TwingateClient(TENANT, API_KEY) as client:
            with pytest.raises(TwingateAPIError, match="Server error 500 after 5 attempts"):
                await client.connect()

    @patch.object(TwingateClient, "_sleep_backoff", new=AsyncMock())
    async def test_429_retries_then_raises(self, httpx_mock: HTTPXMock) -> None:
        """429 responses are retried up to max retries, then raise."""
        for _ in range(5):
            httpx_mock.add_response(url=GQL_URL, status_code=429, text="Too Many Requests")

        async with TwingateClient(TENANT, API_KEY) as client:
            with pytest.raises(TwingateAPIError, match="Rate limited"):
                await client.connect()

    @patch.object(TwingateClient, "_sleep_backoff", new=AsyncMock())
    async def test_5xx_then_success(self, httpx_mock: HTTPXMock) -> None:
        """A 5xx followed by a 200 succeeds (retry works)."""
        httpx_mock.add_response(url=GQL_URL, status_code=502, text="Bad Gateway")
        httpx_mock.add_response(url=GQL_URL, json=_make_groups_page([_GROUP_NODE]))

        async with TwingateClient(TENANT, API_KEY) as client:
            result = await client.connect()
        assert result is True

    async def test_unexpected_status_code_raises(self, httpx_mock: HTTPXMock) -> None:
        """An unexpected HTTP status (e.g. 418) raises TwingateAPIError."""
        httpx_mock.add_response(url=GQL_URL, status_code=418, text="I'm a teapot")
        async with TwingateClient(TENANT, API_KEY) as client:
            with pytest.raises(TwingateAPIError, match="Unexpected HTTP 418"):
                await client.connect()


# ------------------------------------------------------------------
# AccessInput.to_graphql_dict() tests
# ------------------------------------------------------------------


class TestAccessInput:
    """Tests for AccessInput.to_graphql_dict()."""

    def test_minimal(self) -> None:
        """Only principal_id produces a minimal dict."""
        ai = AccessInput(principal_id="R3JvdXA6MjAw")
        result = ai.to_graphql_dict()
        assert result == {"principalId": "R3JvdXA6MjAw"}

    def test_full(self) -> None:
        """All fields set produces a complete dict including durationSeconds."""
        ai = AccessInput(
            principal_id="R3JvdXA6MjAw",
            security_policy_id="U2VjdXJpdHlQb2xpY3k6MQ",
            expires_at="2026-12-31T23:59:59Z",
            access_policy_mode=AccessPolicyMode.AUTO_LOCK,
            access_policy_duration_seconds=86400,
        )
        result = ai.to_graphql_dict()
        assert result == {
            "principalId": "R3JvdXA6MjAw",
            "securityPolicyId": "U2VjdXJpdHlQb2xpY3k6MQ",
            "expiresAt": "2026-12-31T23:59:59Z",
            "accessPolicy": {"mode": "AUTO_LOCK", "durationSeconds": 86400},
        }

    def test_partial_fields(self) -> None:
        """Only set optional fields appear in the dict."""
        ai = AccessInput(
            principal_id="R3JvdXA6MjAw",
            expires_at="2026-06-01T00:00:00Z",
        )
        result = ai.to_graphql_dict()
        assert result == {
            "principalId": "R3JvdXA6MjAw",
            "expiresAt": "2026-06-01T00:00:00Z",
        }
        assert "securityPolicyId" not in result
        assert "accessPolicy" not in result


# ------------------------------------------------------------------
# Closed client guard test
# ------------------------------------------------------------------


class TestClosedClientGuard:
    """Tests for the closed-client guard in _post()."""

    async def test_post_after_close_raises(self) -> None:
        """Calling _post after close() raises TwingateAPIError."""
        client = TwingateClient(TENANT, API_KEY)
        await client.close()
        with pytest.raises(TwingateAPIError, match="Client is already closed"):
            await client._post("query { __typename }")
