from collections.abc import Iterator

import pytest

from tests.runtime.test_vertical_slice import stack, user  # noqa: F401  (shared by the runtime tests)
from tests.support.servers import Served
from workx.core.settings import Environment
from workx.entrypoints.dev_notes import create_dev_notes_app


@pytest.fixture(scope="module")
def notes() -> Iterator[Served]:
    """Test OAuth authorization server + remote MCP server (``workx dev-notes``)."""
    served = Served(create_dev_notes_app(environment=Environment.TEST, refresh_delay=0.3))
    yield served
    served.stop()
