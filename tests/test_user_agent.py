"""Tests for the Twingate API attribution User-Agent.

Covers the builder string format, the version resolver's fallback chain, and
end-to-end proof (via ``httpx.MockTransport``) that every outbound request
carries the attribution header with the right per-operation label and never
falls back to the httpx default.
"""

from __future__ import annotations

import httpx
import pytest

from src.api.client import _PRODUCT, TwingateClient, build_user_agent
from src.version import get_version

# ---------------------------------------------------------------------------
# Builder: string format
# ---------------------------------------------------------------------------


def test_builder_exact_string_with_op() -> None:
    """A representative op renders the full documented format exactly."""
    result = build_user_agent(version="1.3.0", op="add_access")
    assert result == f"twingate-idp-migrator/1.3.0 (op=add_access) python-httpx/{httpx.__version__}"


def test_builder_comment_omitted_without_op() -> None:
    """With no keys, the parenthesised comment is omitted entirely."""
    result = build_user_agent(version="1.3.0")
    assert result == f"twingate-idp-migrator/1.3.0 python-httpx/{httpx.__version__}"
    assert "(" not in result


def test_builder_http_lib_token_matches_runtime_version() -> None:
    """The httpx token is read at runtime, never hardcoded."""
    result = build_user_agent(version="9.9.9")
    assert result.endswith(f"python-httpx/{httpx.__version__}")


def test_builder_product_token_is_repo_slug() -> None:
    """Product token is the canonical lowercase repo slug."""
    assert _PRODUCT == "twingate-idp-migrator"
    assert build_user_agent(version="1.0.0").startswith("twingate-idp-migrator/1.0.0")


# ---------------------------------------------------------------------------
# Version resolver: fallback chain
# ---------------------------------------------------------------------------


def test_get_version_reads_app_version_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_VERSION wins when set."""
    monkeypatch.setenv("APP_VERSION", "2.5.1")
    assert get_version() == "2.5.1"


def test_get_version_strips_leading_v(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tag-style 'vX.Y.Z' is normalised to 'X.Y.Z'."""
    monkeypatch.setenv("APP_VERSION", "v2.5.1")
    assert get_version() == "2.5.1"


def test_get_version_dev_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no env var and no installed distribution, falls back to 0.0.0-dev."""
    monkeypatch.delenv("APP_VERSION", raising=False)

    def _raise(_name: str) -> str:
        raise ModuleNotFoundError("not installed")

    monkeypatch.setattr("importlib.metadata.version", _raise)
    assert get_version() == "0.0.0-dev"


# ---------------------------------------------------------------------------
# End-to-end: outbound requests carry the header
# ---------------------------------------------------------------------------


def _mock_client(client: TwingateClient, handler) -> None:
    """Bind a MockTransport-backed AsyncClient carrying the client's default headers."""
    client._http = httpx.AsyncClient(
        headers=client._headers,
        transport=httpx.MockTransport(handler),
    )


@pytest.fixture
def captured() -> dict[str, str]:
    return {}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TwingateClient:
    monkeypatch.setenv("APP_VERSION", "1.3.0")
    return TwingateClient(tenant="acme", api_key="secret")


def test_config_level_default_header_set_on_client(client: TwingateClient) -> None:
    """The client always carries a config-level attribution UA (no op comment)."""
    assert client._headers["User-Agent"] == build_user_agent(version="1.3.0")
    assert client._headers["User-Agent"].startswith("twingate-idp-migrator/1.3.0")


@pytest.mark.parametrize(
    "op",
    ["connect", "list_groups", "list_resources", "list_access", "add_access", "remove_access"],
)
async def test_post_sends_op_specific_user_agent(
    client: TwingateClient, captured: dict[str, str], op: str
) -> None:
    """Each op label reaches the wire in the request's User-Agent header."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers["User-Agent"]
        return httpx.Response(200, json={"data": {"ok": True}})

    _mock_client(client, handler)
    await client._post("query { __typename }", op=op)

    expected = f"twingate-idp-migrator/1.3.0 (op={op}) python-httpx/{httpx.__version__}"
    assert captured["ua"] == expected
    # Never the bare httpx default.
    assert captured["ua"].startswith("twingate-idp-migrator/")


async def test_post_without_op_uses_config_level_header(
    client: TwingateClient, captured: dict[str, str]
) -> None:
    """A request with no op falls back to the client default UA, not httpx's."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers["User-Agent"]
        return httpx.Response(200, json={"data": {"ok": True}})

    _mock_client(client, handler)
    await client._post("query { __typename }")

    assert captured["ua"] == build_user_agent(version="1.3.0")
    assert "(op=" not in captured["ua"]


async def test_connect_end_to_end_carries_connect_op(
    client: TwingateClient, captured: dict[str, str]
) -> None:
    """A real public method (connect) wires its op through to the header."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers["User-Agent"]
        return httpx.Response(
            200,
            json={
                "data": {
                    "groups": {
                        "edges": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            },
        )

    _mock_client(client, handler)
    ok = await client.connect()

    assert ok is True
    assert captured["ua"].endswith(f"python-httpx/{httpx.__version__}")
    assert "(op=connect)" in captured["ua"]
