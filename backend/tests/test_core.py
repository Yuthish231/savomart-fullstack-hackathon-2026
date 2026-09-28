import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.llm.provider import LLMUnavailable, NullProvider, parse_json_object


def test_password_roundtrip():
    h = hash_password("s3cret")
    assert verify_password("s3cret", h)
    assert not verify_password("wrong", h)


def test_token_carries_role():
    claims = decode_access_token(create_access_token("abc", "BDM"))
    assert claims["sub"] == "abc" and claims["role"] == "BDM"


@pytest.mark.parametrize(
    "raw",
    [
        '{"ok": true}',
        '```json\n{"ok": true}\n```',
        'Sure, here you go: {"ok": true} hope that helps',
    ],
)
def test_parse_json_object_recovers(raw):
    assert parse_json_object(raw) == {"ok": True}


@pytest.mark.parametrize("raw", ["no json here", "[1, 2]", '{"ok": tru'])
def test_parse_json_object_rejects(raw):
    with pytest.raises(LLMUnavailable):
        parse_json_object(raw)


def test_null_provider_signals_unavailable():
    with pytest.raises(LLMUnavailable):
        NullProvider().complete_json("sys", "user")
