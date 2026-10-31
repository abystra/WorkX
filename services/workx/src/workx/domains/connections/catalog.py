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
    token_body: str = "form"  # noqa: S105 (a request encoding, not a secret)


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
                token_body="json",  # noqa: S106
            ),
            config_fields=("client_id", "client_secret"),
        ),
        Connector(
            "notes",
            "Notes (OAuth test provider)",
            "B",
            "oauth",
            "user",
            ("notes_create", "notes_list"),
            oauth=OAuthEndpoints(authorize_url="", token_url="", scopes=("notes.write", "offline_access")),
            config_fields=("client_id", "client_secret", "base_url"),
        ),
    )
}
TOOL_CONNECTOR = {tool: c.id for c in CONNECTORS.values() for tool in c.tools}


def get(connector_id: str) -> Connector | None:
    return CONNECTORS.get(connector_id)
