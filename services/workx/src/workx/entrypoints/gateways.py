"""Trusted gateway processes. Each loads only its own settings (the model gateway alone holds the model key)."""

from __future__ import annotations

from fastapi import FastAPI

from workx.core.logging import configure


def model_gateway() -> FastAPI:
    from workx.core.settings import ModelGatewaySettings
    from workx.trusted.model_gateway.app import create_model_gateway_app

    settings = ModelGatewaySettings()
    configure(settings.log_level)
    return create_model_gateway_app(settings)


def tool_gateway() -> FastAPI:
    from workx.core.settings import ToolGatewaySettings
    from workx.trusted.tool_gateway.app import create_tool_gateway_app

    settings = ToolGatewaySettings()
    configure(settings.log_level)
    return create_tool_gateway_app(settings)


def dev_crm() -> FastAPI:
    from workx.core.settings import BaseWorkxSettings, ToolGatewaySettings
    from workx.entrypoints.dev_crm import create_dev_crm_app

    return create_dev_crm_app(
        ToolGatewaySettings().crm_api_key.get_secret_value() or "dev-crm-key",
        environment=BaseWorkxSettings().environment,
    )


def dev_model() -> FastAPI:
    import os

    from workx.core.settings import BaseWorkxSettings
    from workx.entrypoints.dev_model import UPSTREAM_KEY, create_dev_model_app

    key = os.environ.get("WORKX_DEV_MODEL_KEY", UPSTREAM_KEY)
    return create_dev_model_app(key=key, environment=BaseWorkxSettings().environment)
