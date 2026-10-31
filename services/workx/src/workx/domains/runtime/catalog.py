"""Tools an Attempt may call through the Tool Gateway by default (names only; the gateway owns the tools).

Per-agent tool bindings arrive with connections (P-07); until then every Attempt gets the platform tools."""

DEFAULT_TOOLS: tuple[str, ...] = ("crm_list_accounts", "crm_create_note", "crm_send_email", "web_fetch")
