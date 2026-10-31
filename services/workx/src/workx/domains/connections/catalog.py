"""Connector definitions (Part 6 §1, §3.1 connector_definitions). Code, reviewed like any other change.

``cls`` is the integration class: 0 no auth, A API key/header, B user OAuth, C app credentials exchanged.
``identity`` says whose credential a call uses: the initiating member's (user) or an org-shared one (app).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OAuthEndpoints:
    authorize_url: str
    token_url: str
    revoke_url: str | None = None
    scopes: tuple[str, ...] = ()
    # Feishu's v2 token endpoint takes JSON and app credentials in the body (client_secret_post).
    exchange_format: str = "form"


@dataclass(frozen=True)
class Connector:
    id: str
    name: str
    cls: str
    auth: str  # none | api_key | oauth
    identity: str  # app | user
    tools: tuple[str, ...]
    default_installed: bool = False
    oauth: OAuthEndpoints | None = None
    config_fields: tuple[str, ...] = field(default=())
    # Remote MCP server (URL in the installation's ``base_url``): platform tool name → the server's tool name.
    # Its OAuth endpoints are discovered (RFC 9728 → RFC 8414) and, without a configured client_id, the client is
    # registered dynamically (RFC 7591).
    remote_mcp: dict[str, str] | None = None
    # Holds a channel binding's bot secrets (usage class "channel"); not offered as a tool connection.
    channel: bool = False


CONNECTORS: dict[str, Connector] = {
    c.id: c
    for c in (
        Connector("web", "Web fetch", "0", "none", "app", ("web_fetch",), default_installed=True),
        Connector(
            "crm", "CRM (test API)", "A", "api_key", "app", ("crm_list_accounts", "crm_create_note", "crm_send_email")
        ),
        Connector(
            "feishu-docs",
            "Feishu Docs (user)",
            "B",
            "oauth",
            "user",
            ("feishu_docs_search", "feishu_docs_create"),
            oauth=OAuthEndpoints(
                authorize_url="https://accounts.feishu.cn/open-apis/authen/v1/authorize",
                token_url="https://open.feishu.cn/open-apis/authen/v2/oauth/token",  # noqa: S106
                scopes=("docx:document", "drive:drive:readonly", "offline_access"),
                exchange_format="json",
            ),
            config_fields=("client_id", "client_secret"),
        ),
        Connector(
            "notes",
            "Notes (remote MCP, OAuth)",
            "B",
            "oauth",
            "user",
            ("notes_create", "notes_list"),
            oauth=OAuthEndpoints(authorize_url="", token_url="", scopes=("notes.read", "notes.write")),
            config_fields=("base_url", "client_id"),
            remote_mcp={"notes_create": "create_note", "notes_list": "list_notes"},
        ),
    )
}
CONNECTORS.update(
    {
        c.id: c
        for c in (
            Connector("channel-feishu", "Feishu bot (channel)", "C", "app_secret", "app", (), channel=True),
            Connector("channel-wecom", "WeCom app (channel)", "C", "app_secret", "app", (), channel=True),
        )
    }
)
TOOL_CONNECTOR = {tool: c.id for c in CONNECTORS.values() for tool in c.tools}


def get(connector_id: str) -> Connector | None:
    return CONNECTORS.get(connector_id)
