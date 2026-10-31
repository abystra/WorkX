import pytest
from pydantic import ValidationError

from workx.core.settings import ApiSettings, Environment


def test_test_seed_refused_in_production() -> None:
    with pytest.raises(ValidationError):
        ApiSettings(environment=Environment.PRODUCTION, enable_test_seed=True)


def test_insecure_cookie_refused_in_staging() -> None:
    with pytest.raises(ValidationError):
        ApiSettings(environment=Environment.STAGING, session_cookie_secure=False)
