import json

from laya_agent.audit import audit_events
from laya_agent.contracts import state_hash
from laya_agent.telemetry.events import bound, is_secret_key, redact
from laya_agent.telemetry.jsonl import read_events


def test_redaction_drops_secret_keys_and_strings_but_keeps_usage():
    data = {"token": "abc", "Authorization": "Bearer abc", "api_key": "k", "nested": {"x_api_key": "k"},
            "usage": {"input_tokens": 12}, "msg": "key is s3cr3t here", "session_id": "s-1"}
    out = redact(data, ("s3cr3t",))
    assert out["token"] == out["Authorization"] == out["api_key"] == "<redacted>"
    assert out["nested"]["x_api_key"] == "<redacted>"
    assert out["usage"] == {"input_tokens": 12}
    assert out["session_id"] == "s-1"
    assert "s3cr3t" not in out["msg"]
    assert not is_secret_key("input_tokens")


def test_bound_keeps_small_values_and_hashes_large_ones():
    assert bound({"a": 1}, 100) == {"a": 1}
    big = bound("x" * 5000, 100)
    assert big["_truncated"] and big["_chars"] > 100 and len(big["_sha256"]) == 64


def test_log_is_persisted_per_event_and_survives_a_torn_line(make_log, tmp_path):
    log = make_log()
    log.emit("run_start", note="hello", token="should-not-appear")
    log.emit("decision", decision_id="d1")
    # Simulate a crash mid-write: a partial line at the end of the file.
    with open(tmp_path / "run.jsonl", "a", encoding="utf-8") as fh:
        fh.write('{"seq": 3, "type": "subm')
    events = read_events(tmp_path / "run.jsonl")
    assert [e["seq"] for e in events] == [1, 2]
    assert events[0]["token"] == "<redacted>"
    assert all(e["run_id"] == "test-run" and e["env"] == "LOCAL_FIXTURE" for e in events)


def test_sink_failure_does_not_stop_logging(make_log, tmp_path):
    def broken(_):
        raise RuntimeError("viewer crashed")

    log = make_log(sinks=[broken])
    log.emit("run_start")
    assert len(read_events(tmp_path / "run.jsonl")) == 1


def test_state_hash_is_order_independent():
    assert state_hash({"a": 1, "b": [1, 2]}) == state_hash({"b": [1, 2], "a": 1})


def test_audit_flags_moves_without_a_valid_laya_decision():
    base = {"run_id": "r", "env": "LOCAL_FIXTURE"}
    good = [
        {**base, "seq": 1, "type": "decision", "decision_id": "d1", "valid": True, "chosen_action_id": "up", "laya_response": {"answers": {}}},
        {**base, "seq": 2, "type": "submission", "decision_id": "d1", "action_id": "up"},
    ]
    assert audit_events(good)["ok"]
    orphan = good + [{**base, "seq": 3, "type": "submission", "decision_id": "nope", "action_id": "up"}]
    assert not audit_events(orphan)["ok"]
    swapped = [good[0], {**base, "seq": 2, "type": "submission", "decision_id": "d1", "action_id": "down"}]
    report = audit_events(swapped)
    assert not report["ok"] and "Laya chose" in report["problems"][0]
    json.dumps(report)
