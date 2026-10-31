"""OAuth protocol details that the dev provider does not exercise (Part 6 §4): RFC 8414/9728 well-known paths,
Feishu's JSON token endpoint with client_secret_post and errors wrapped in a 200 response."""

from __future__ import annotations

import json

import httpx
import pytest

from workx.domains.connections import catalog
from workx.trusted.credentials import oauth


def test_well_known_paths_insert_the_segment_before_the_path() -> None:
    assert oauth.well_known("https://mcp.example.com/v1/mcp", "oauth-protected-resource") == [
        "https://mcp.example.com/.well-known/oauth-protected-resource/v1/mcp",
        "https://mcp.example.com/.well-known/oauth-protected-resource",
    ]
    assert oauth.well_known("https://as.example.com", "oauth-authorization-server") == [
        "https://as.example.com/.well-known/oauth-authorization-server"
    ]


def test_authorize_url_carries_pkce_state_and_resource() -> None:
    endpoints = oauth.Endpoints("https://as/authorize", "https://as/token", None, ("a", "b"), resource="https://rs/mcp")
    verifier, challenge = oauth.pkce_pair()
    url = httpx.URL(oauth.authorize_url(endpoints, "cid", "https://app/cb", "st", challenge))
    assert dict(url.params) == {
        "response_type": "code",
        "client_id": "cid",
        "redirect_uri": "https://app/cb",
        "state": "st",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "a b",
        "resource": "https://rs/mcp",
    }
    assert len(verifier) >= 43


def test_feishu_token_exchange_uses_json_and_reads_wrapped_errors() -> None:
    seen: list[dict[str, str]] = []

    def feishu(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if body["code"] == "bad":
            return httpx.Response(200, json={"code": 20050, "error": "invalid_grant", "error_description": "expired"})
        return httpx.Response(
            200,
            json={
                "code": 0,
                "access_token": "u-1",
                "refresh_token": "ur-1",
                "expires_in": 7200,
                "scope": "docx:document",
            },
        )

    connector = catalog.CONNECTORS["feishu-docs"]
    endpoints = oauth.endpoints_for(connector, {"client_id": "cli_1"}, httpx.Client())
    assert endpoints.exchange_format == "json" and endpoints.authorize_url.startswith("https://accounts.feishu.cn/")
    http = httpx.Client(transport=httpx.MockTransport(feishu))
    tokens = oauth.exchange_code(http, endpoints, "cli_1", "app-secret", "good", "verifier", "https://app/cb")
    assert (tokens.access_token, tokens.refresh_token, tokens.scopes) == ("u-1", "ur-1", ["docx:document"])
    assert seen[0] == {
        "grant_type": "authorization_code",
        "code": "good",
        "code_verifier": "verifier",
        "redirect_uri": "https://app/cb",
        "client_id": "cli_1",
        "client_secret": "app-secret",
    }
    with pytest.raises(oauth.OAuthFailure):
        oauth.exchange_code(http, endpoints, "cli_1", "app-secret", "bad", "verifier", "https://app/cb")
