"""WorkX-hosted test CRM API for the class-A connector in the vertical slice (Part 14 §2): ``workx dev-crm``.

It counts every call so tests can prove a retried Attempt did not repeat a write. Development and tests only.
"""

from __future__ import annotations

import itertools
import threading
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from workx.core.settings import Environment

ACCOUNTS = [
    {"id": "acc_001", "name": "Northwind Traders", "annual_revenue": 4_200_000, "owner": "Alex"},
    {"id": "acc_002", "name": "Contoso Ltd", "annual_revenue": 3_100_000, "owner": "Mia"},
    {"id": "acc_003", "name": "Fabrikam", "annual_revenue": 2_750_000, "owner": "Alex"},
    {"id": "acc_004", "name": "Tailspin Toys", "annual_revenue": 1_900_000, "owner": "Bob"},
    {"id": "acc_005", "name": "Wingtip Toys", "annual_revenue": 1_250_000, "owner": "Mia"},
]


class NoteIn(BaseModel):
    account_id: str
    text: str


class EmailIn(BaseModel):
    account_id: str
    subject: str
    body: str


def create_dev_crm_app(api_key: str, *, environment: Environment = Environment.DEVELOPMENT) -> FastAPI:
    if environment in (Environment.STAGING, Environment.PRODUCTION):
        raise RuntimeError("The test CRM must not run in staging or production.")
    app = FastAPI(title="WorkX test CRM", docs_url=None, redoc_url=None, openapi_url=None)
    lock = threading.Lock()
    counter = itertools.count(1)
    state: dict[str, Any] = {"notes": [], "emails": [], "calls": {"list": 0, "note": 0, "email": 0}}
    app.state.crm = state

    def check(key: str | None) -> None:
        if key != api_key:
            raise HTTPException(401, "invalid api key")

    @app.get("/accounts")
    def accounts(limit: int = 20, x_api_key: str | None = Header(default=None)) -> list[dict[str, Any]]:
        check(x_api_key)
        with lock:
            state["calls"]["list"] += 1
        return ACCOUNTS[:limit]

    @app.post("/notes", status_code=201)
    def note(body: NoteIn, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check(x_api_key)
        with lock:
            state["calls"]["note"] += 1
            record = {"id": f"note_{next(counter)}", **body.model_dump()}
            state["notes"].append(record)
        return record

    @app.post("/emails", status_code=201)
    def email(body: EmailIn, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check(x_api_key)
        with lock:
            state["calls"]["email"] += 1
            record = {"id": f"email_{next(counter)}", **body.model_dump()}
            state["emails"].append(record)
        return record

    @app.get("/_stats")
    def stats() -> dict[str, Any]:
        return {"calls": dict(state["calls"]), "notes": len(state["notes"]), "emails": len(state["emails"])}

    return app
