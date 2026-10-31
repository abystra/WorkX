"""Test alias for the development model (src/workx/entrypoints/dev_model.py)."""

from workx.entrypoints.dev_model import SCRIPTS, UPSTREAM_KEY, create_dev_model_app

create_fake_anthropic = create_dev_model_app

__all__ = ["SCRIPTS", "UPSTREAM_KEY", "create_fake_anthropic"]
