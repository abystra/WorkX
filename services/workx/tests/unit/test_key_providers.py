"""KeyProvider adapters at the protocol level (Part 6 §3.2): OpenBao Transit over HTTP, AWS KMS against the
botocore service model. Real OpenBao/KMS verification is listed in the completion matrix (B-15)."""

from __future__ import annotations

import base64
import json
import os

import boto3
import httpx
import pytest
from botocore.stub import Stubber
from cryptography.exceptions import InvalidTag

from workx.core.settings import TrustedSettings
from workx.trusted.credentials import keys

KEY_REF = "ten_1/cred_1"


def test_local_provider_binds_the_key_ref() -> None:
    provider = keys.LocalKeyProvider(os.urandom(32))
    dek = os.urandom(32)
    wrapped, version = provider.wrap(KEY_REF, dek)
    assert version == 1 and dek not in wrapped
    assert provider.unwrap(KEY_REF, wrapped, version) == dek
    with pytest.raises(InvalidTag):
        provider.unwrap("ten_2/cred_1", wrapped, version)


def test_openbao_transit_protocol() -> None:
    """A fake Transit engine: checks the token, path and payload shape OpenBao expects."""
    kek: dict[str, bytes] = {}
    calls: list[str] = []

    def transit(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Vault-Token"] == "s.token"
        _, _, mount, action, name = request.url.path.split("/")
        calls.append(f"{mount}/{action}/{name}")
        body = json.loads(request.content)
        if action == "encrypt":
            plaintext = base64.b64decode(body["plaintext"])
            kek.setdefault(name, os.urandom(1))
            blob = bytes(b ^ kek[name][0] for b in plaintext)
            return httpx.Response(200, json={"data": {"ciphertext": f"vault:v3:{base64.b64encode(blob).decode()}"}})
        version, blob64 = body["ciphertext"].split(":")[1:]
        assert version == "v3"
        plaintext = bytes(b ^ kek[name][0] for b in base64.b64decode(blob64))
        return httpx.Response(200, json={"data": {"plaintext": base64.b64encode(plaintext).decode()}})

    provider = keys.OpenBaoTransitProvider(
        "https://bao.internal", "s.token", "workx-transit", http=httpx.Client(transport=httpx.MockTransport(transit))
    )
    dek = os.urandom(32)
    wrapped, version = provider.wrap(KEY_REF, dek)
    assert version == 3 and wrapped.startswith(b"vault:v3:")
    assert provider.unwrap(KEY_REF, wrapped, version) == dek
    assert calls == ["workx-transit/encrypt/ten_1-cred_1", "workx-transit/decrypt/ten_1-cred_1"]


def test_aws_kms_requests_match_the_service_model() -> None:
    client = boto3.client("kms", region_name="eu-central-1", aws_access_key_id="x", aws_secret_access_key="y")
    arn = "arn:aws:kms:eu-central-1:111122223333:key/1234abcd-12ab-34cd-56ef-1234567890ab"
    dek = os.urandom(32)
    with Stubber(client) as stub:
        stub.add_response(
            "encrypt",
            {"CiphertextBlob": b"wrapped", "KeyId": arn},
            {"KeyId": arn, "Plaintext": dek, "EncryptionContext": {"key_ref": KEY_REF}},
        )
        stub.add_response(
            "decrypt",
            {"Plaintext": dek, "KeyId": arn},
            {"CiphertextBlob": b"wrapped", "EncryptionContext": {"key_ref": KEY_REF}},
        )
        provider = keys.AwsKmsProvider(arn, client=client)
        wrapped, version = provider.wrap(KEY_REF, dek)
        assert (wrapped, version) == (b"wrapped", 1)
        assert provider.unwrap(KEY_REF, wrapped, version) == dek
        stub.assert_no_pending_responses()


def test_provider_selection_from_settings() -> None:
    bao = keys.from_settings(TrustedSettings(key_provider="openbao:https://bao.internal:8200?mount=kv-transit"))
    assert isinstance(bao, keys.OpenBaoTransitProvider)
    assert (bao.base_url, bao.mount) == ("https://bao.internal:8200", "kv-transit")
    assert isinstance(keys.from_settings(TrustedSettings()), keys.LocalKeyProvider)
    with pytest.raises(ValueError, match="WORKX_KEY_PROVIDER"):
        keys.from_settings(TrustedSettings(key_provider="plaintext"))
