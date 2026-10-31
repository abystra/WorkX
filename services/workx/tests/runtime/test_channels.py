"""J6 (Part 8; backlog B-21): chat message → verified callback → linked member → task → reply in the chat.

Callbacks are signed and encrypted exactly as Feishu and WeCom send them; replies go to test platform APIs.
Covers url verification, signature/timestamp/token rejection, replay without duplicates, account linking by
code, group @mention rule, group privacy (link-only replies), binding changes blocking replies, retries."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.conftest import ProvisionedDatabase
from tests.integration.test_knowledge import make_source, upload
from tests.runtime.test_vertical_slice import Stack, User, start_one
from tests.support import chat_events as chat
from tests.support.servers import Served
from workx.core.db import Database
from workx.core.settings import Environment, TrustedSettings
from workx.domains.connections.broker_client import BrokerClient
from workx.domains.knowledge import service as knowledge
from workx.entrypoints.dev_channels import create_dev_channels_app
from workx.entrypoints.worker import build_context
from workx.platform import jobs
from workx.trusted.broker.app import create_broker_app


@pytest.fixture(scope="module")
def platforms() -> Iterator[Served]:
    served = Served(
        create_dev_channels_app(
            environment=Environment.TEST,
            apps={"cli_app": chat.FEISHU_SECRETS["app_secret"], "ww_corp": chat.WECOM_SECRETS["secret"]},
        )
    )
    yield served
    served.stop()


@pytest.fixture(scope="module")
def channel_broker(platforms: Served, test_database: ProvisionedDatabase, broker_db: Database) -> TestClient:
    settings = TrustedSettings(
        environment=Environment.TEST,
        broker_database_url=test_database.broker_url,
        feishu_base_url=platforms.url,
        wecom_base_url=platforms.url,
    )
    return TestClient(create_broker_app(settings, broker_db))


@pytest.fixture
def work(api_app: FastAPI, db: Database, owner_db: Database, channel_broker: TestClient) -> Callable[[], None]:
    def run() -> None:
        with owner_db.transaction() as session:  # retries scheduled with backoff run now
            session.execute(text("UPDATE jobs SET run_after = now() WHERE status = 'queued' AND kind LIKE 'channel%'"))
        ctx = build_context(api_app.state.workx.settings, db)
        services = api_app.state.workx.services
        ctx.services["broker"] = BrokerClient("http://testserver", "workx-dev-broker-token", channel_broker)
        ctx.services["knowledge"] = knowledge.Services(db, services["objects"], services["embeddings"])
        for _ in range(20):
            counts = jobs.run_once(ctx, "w-channels")
            if not sum(n for status, n in counts.items() if status != "dispatched"):
                break

    return run


def sent(platforms: Served) -> list[dict[str, Any]]:
    return list(httpx.get(f"{platforms.url}/_sent").json())


def post_feishu(client: TestClient, binding: dict[str, Any], event: dict[str, Any], **kw: Any) -> httpx.Response:
    body, headers = chat.feishu_request(event, **kw)
    path = "/api/v1" + binding["webhook_url"].split("/api/v1", 1)[1]
    return client.post(path, content=body, headers=headers)


def feishu_binding(user: User, **extra: Any) -> dict[str, Any]:
    response = user.client.post(
        f"{user.t}/channel-bindings",
        json={
            "platform": "feishu",
            "method": "feishu-bot",
            "name": "WorkX bot",
            "agent_id": user.agent,
            "config": {"app_id": "cli_app", "bot_open_id": chat.BOT_OPEN_ID},
            "secrets": chat.FEISHU_SECRETS,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def link(user: User, binding: dict[str, Any], anonymous: TestClient, work: Callable[[], None], sender: str) -> None:
    code = user.client.post(f"{user.t}/channel-bindings/{binding['id']}/link-code").json()["code"]
    assert post_feishu(anonymous, binding, chat.feishu_message(sender=sender, text=f"link {code}")).status_code == 200
    work()


def runs(user: User) -> list[dict[str, Any]]:
    return list(user.client.get(f"{user.t}/channel-runs").json())


def run_task(stack: Stack, task_id: str) -> str:
    return stack.orchestrator.run(start_one(stack, task_id))


def test_feishu_message_becomes_a_task_and_the_answer_is_delivered(
    stack: Stack,
    user: User,
    new_client: Callable[[], TestClient],
    platforms: Served,
    work: Callable[[], None],
) -> None:
    anonymous = new_client()
    binding = feishu_binding(user)
    assert binding["configured"] and binding["webhook_url"].endswith("/events")
    # URL verification (encrypted, unsigned) answers the challenge.
    challenge = {"type": "url_verification", "challenge": "c-123", "token": chat.FEISHU_SECRETS["verification_token"]}
    body, _ = chat.feishu_request(challenge)
    path = "/api/v1" + binding["webhook_url"].split("/api/v1", 1)[1]
    assert anonymous.post(path, content=body).json() == {"challenge": "c-123"}
    # An unlinked sender gets a notice, never a task.
    before = len(sent(platforms))
    assert post_feishu(anonymous, binding, chat.feishu_message(sender="ou_pat", text="hello")).status_code == 200
    work()
    [first] = runs(user)
    assert first["stage"] == "unlinked" and first["task_id"] is None
    assert "link" in json.loads(sent(platforms)[-1]["content"])["text"].lower() and len(sent(platforms)) == before + 1
    # Linking with a one-time code.
    link(user, binding, anonymous, work, "ou_pat")
    assert json.loads(sent(platforms)[-1]["content"])["text"].startswith("Linked")
    # The request runs as the linked member and the answer is delivered as a reply to the message.
    event = chat.feishu_message(sender="ou_pat", text="Build a list of our top accounts from the CRM", event_id="evt-1")
    assert post_feishu(anonymous, binding, event).status_code == 200
    work()
    run = next(r for r in runs(user) if r["event_id"] == "evt-1")
    task = user.get(run["task_id"])
    assert task["kind"] == "channel" and task["status"] == "queued"
    assert run_task(stack, run["task_id"]) == "succeeded"
    work()
    reply = sent(platforms)[-1]
    assert reply["reply_to"] == event["event"]["message"]["message_id"]
    assert (
        "Here are your top accounts" in json.loads(reply["content"])["text"]
        and run["task_id"] in json.loads(reply["content"])["text"]
    )
    run = next(r for r in runs(user) if r["event_id"] == "evt-1")
    assert run["stage"] == "delivered" and run["delivery_status"] == "delivered"
    # The platform retries the same event: recorded once, no second task.
    assert post_feishu(anonymous, binding, event).status_code == 200
    work()
    again = [r for r in runs(user) if r["event_id"] == "evt-1"]
    assert len(again) == 1 and again[0]["replay_count"] == 1


def test_forged_stale_or_foreign_callbacks_are_rejected(user: User, new_client: Callable[[], TestClient]) -> None:
    anonymous = new_client()
    binding = feishu_binding(user)
    message = chat.feishu_message(sender="ou_x", text="hi")
    assert post_feishu(anonymous, binding, message, sign_key="wrong-key").status_code == 401
    assert post_feishu(anonymous, binding, message, timestamp=1_600_000_000).status_code == 401
    assert (
        post_feishu(anonymous, binding, chat.feishu_message(sender="ou_x", text="hi", token="other")).status_code == 401
    )
    assert anonymous.post("/api/v1/channels/feishu/not-a-binding/events", content=b"{}").status_code == 404
    assert runs(user) == []


def test_group_rules_and_private_content_stay_out_of_groups(
    stack: Stack,
    user: User,
    new_client: Callable[[], TestClient],
    platforms: Served,
    work: Callable[[], None],
) -> None:
    anonymous = new_client()
    binding = feishu_binding(user)
    link(user, binding, anonymous, work, "ou_sam")
    # Without an @mention the bot ignores group chatter.
    post_feishu(
        anonymous, binding, chat.feishu_message(sender="ou_sam", text="lunch?", chat_type="group", event_id="g-1")
    )
    work()
    assert next(r for r in runs(user) if r["event_id"] == "g-1")["stage"] == "ignored"
    # The workmate answers from a private file: the group only gets a link.
    file = upload(
        user.client, user.t, "salaries.md", b"# Pay\n\nHotels are reimbursed per night at 999 EUR.\n", "text/markdown"
    )
    source = make_source(user.client, user.t, file["id"])
    work()
    user.client.put(f"{user.t}/agents/{user.agent}/knowledge", json={"source_ids": [source["id"]]})
    ask = chat.feishu_message(
        sender="ou_sam",
        text="SCENARIO:knowledge hotels reimbursed per night",
        chat_type="group",
        event_id="g-2",
        mention_bot=True,
    )
    post_feishu(anonymous, binding, ask)
    work()
    run = next(r for r in runs(user) if r["event_id"] == "g-2")
    assert run["source"]["mention"] is True and run_task(stack, run["task_id"]) == "succeeded"
    work()
    reply = json.loads(sent(platforms)[-1]["content"])["text"]
    assert "private to the requester" in reply and "999" not in reply


def test_binding_changes_block_replies_and_deliveries_retry(
    stack: Stack,
    user: User,
    new_client: Callable[[], TestClient],
    platforms: Served,
    work: Callable[[], None],
) -> None:
    anonymous = new_client()
    binding = feishu_binding(user)
    link(user, binding, anonymous, work, "ou_lee")
    post_feishu(
        anonymous,
        binding,
        chat.feishu_message(sender="ou_lee", text="Build a list of our top accounts from the CRM", event_id="b-1"),
    )
    work()
    run = next(r for r in runs(user) if r["event_id"] == "b-1")
    changed = user.client.patch(f"{user.t}/channel-bindings/{binding['id']}", json={"capabilities": ["reply"]})
    assert changed.json()["revision"] == binding["revision"] + 1
    assert run_task(stack, run["task_id"]) == "succeeded"
    work()
    run = next(r for r in runs(user) if r["event_id"] == "b-1")
    assert run["delivery_status"] == "blocked" and run["error_code"] == "binding_changed"
    # A person retries under the current rules; the platform fails once, then the retry delivers.
    httpx.post(f"{platforms.url}/_fail", json={"count": 1})
    assert user.client.post(f"{user.t}/channel-runs/{run['id']}/retry-delivery").status_code == 200
    work()
    work()
    run = next(r for r in runs(user) if r["event_id"] == "b-1")
    assert run["delivery_status"] == "delivered" and run["delivery_attempts"] == 2


def test_wecom_app_callbacks_link_and_reply(
    stack: Stack,
    user: User,
    new_client: Callable[[], TestClient],
    platforms: Served,
    work: Callable[[], None],
) -> None:
    anonymous = new_client()
    created = user.client.post(
        f"{user.t}/channel-bindings",
        json={
            "platform": "wecom",
            "method": "wecom-app",
            "name": "WorkX app",
            "agent_id": user.agent,
            "config": {"corp_id": "ww_corp", "agent_id": "1000002"},
            "secrets": chat.WECOM_SECRETS,
        },
    )
    assert created.status_code == 201, created.text
    binding = created.json()
    path = "/api/v1" + binding["webhook_url"].split("/api/v1", 1)[1]
    # URL verification: the decrypted echostr is returned as plain text.
    from workx.trusted.channels import crypto

    echo = crypto.wecom_encrypt(chat.WECOM_SECRETS["encoding_aes_key"], "echo-42", "ww_corp")
    ts, nonce = "1700000000", "n1"
    signature = crypto.wecom_signature(chat.WECOM_SECRETS["token"], ts, nonce, echo)
    verified = anonymous.get(
        path, params={"msg_signature": signature, "timestamp": ts, "nonce": nonce, "echostr": echo}
    )
    assert verified.status_code == 200 and verified.text == "echo-42"
    code = user.client.post(f"{user.t}/channel-bindings/{binding['id']}/link-code").json()["code"]
    body, query = chat.wecom_request(chat.wecom_text("zhangsan", f"link {code}"), "ww_corp")
    assert anonymous.post(path, params=query, content=body).text == "success"
    work()
    assert sent(platforms)[-1] == {**sent(platforms)[-1], "platform": "wecom", "to": "zhangsan"}
    body, query = chat.wecom_request(
        chat.wecom_text("zhangsan", "Build a list of our top accounts from the CRM", "77"), "ww_corp"
    )
    anonymous.post(path, params=query, content=body)
    work()
    run = next(r for r in runs(user) if r["event_id"] == "77")
    assert run_task(stack, run["task_id"]) == "succeeded"
    work()
    assert "Here are your top accounts" in sent(platforms)[-1]["content"]
    # A callback encrypted for another corp is refused.
    body, query = chat.wecom_request(chat.wecom_text("zhangsan", "hi"), "ww_other")
    assert anonymous.post(path, params=query, content=body).status_code == 401
