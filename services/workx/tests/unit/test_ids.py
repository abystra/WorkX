import time
import uuid

from workx.core import ids


def test_round_trip_and_prefix() -> None:
    value, external = ids.new("task")
    assert external.startswith("tsk_") and len(external) == 30
    assert ids.decode("task", external) == value
    assert ids.decode("task", external.lower()) == value


def test_wrong_kind_or_malformed_is_none() -> None:
    _, external = ids.new("task")
    assert ids.decode("agent", external) is None
    assert ids.decode("task", "tsk_short") is None
    assert ids.decode("task", "tsk_" + "U" * 26) is None  # U is not in the Crockford alphabet
    assert ids.decode("task", "tsk_" + "Z" * 26) is None  # overflows 128 bits


def test_uuid7_is_versioned_and_time_ordered() -> None:
    first = ids.uuid7()
    time.sleep(0.002)
    second = ids.uuid7()
    assert first.version == 7 and first.variant == uuid.RFC_4122
    assert first < second
    assert ids.encode("task", first) < ids.encode("task", second)
