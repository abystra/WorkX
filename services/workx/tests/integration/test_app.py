from fastapi import APIRouter
from fastapi.testclient import TestClient

from tests.conftest import ProvisionedDatabase, make_settings
from workx.core.db import Database
from workx.core.errors import ApiError
from workx.entrypoints.api import create_app


def _client_with(test_database: ProvisionedDatabase, db: Database, router: APIRouter) -> TestClient:
    app = create_app(make_settings(test_database), db)
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_health_and_readiness(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    response = client.get("/readyz")
    assert response.status_code == 200 and response.json() == {"status": "ready"}
    assert response.headers["x-request-id"].startswith("req_")


def test_readiness_reports_unreachable_database(test_database: ProvisionedDatabase) -> None:
    broken = Database.connect("postgresql+psycopg://workx_app:wrong@127.0.0.1:1/none")
    with TestClient(create_app(make_settings(test_database), broken), raise_server_exceptions=False) as c:
        response = c.get("/readyz")
    assert response.status_code == 503
    assert response.json()["code"] == "UPSTREAM_UNAVAILABLE" and response.json()["retryable"] is True


def test_problem_details_shapes(test_database: ProvisionedDatabase, db: Database) -> None:
    router = APIRouter()

    @router.get("/boom")
    def boom() -> None:
        raise ApiError(409, "INVALID_STATE", "Task already finished.", data={"status": "succeeded"})

    @router.get("/crash")
    def crash() -> None:
        raise RuntimeError("secret sk-ant-api03-SHOULDNOTLEAK")

    @router.get("/typed")
    def typed(limit: int) -> dict[str, int]:
        return {"limit": limit}

    with _client_with(test_database, db, router) as c:
        conflict = c.get("/boom", headers={"X-Request-Id": "req_test123"})
        assert conflict.status_code == 409
        assert conflict.headers["content-type"] == "application/problem+json"
        body = conflict.json()
        assert body == {
            "type": "https://docs.workx.example/errors/invalid-state",
            "title": "Conflict",
            "status": 409,
            "code": "INVALID_STATE",
            "detail": "Task already finished.",
            "request_id": "req_test123",
            "retryable": False,
            "data": {"status": "succeeded"},
        }
        crash = c.get("/crash")
        assert crash.status_code == 500 and crash.json()["code"] == "INTERNAL"
        assert crash.json()["request_id"].startswith("req_")
        assert "SHOULDNOTLEAK" not in crash.text
        invalid = c.get("/typed?limit=abc")
        assert invalid.status_code == 400 and invalid.json()["code"] == "VALIDATION_FAILED"
        assert c.get("/api/v1/nothing-here").json()["code"] == "NOT_FOUND"
