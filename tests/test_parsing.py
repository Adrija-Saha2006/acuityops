from app.parsing import parse_logs_from_json


def test_parse_valid_rows():
    raw = '[{"metric":"uptime","value":99.2,"unit":"percent"},{"metric":"response_time","value":1.5,"unit":"hours"}]'
    readings = parse_logs_from_json(raw)
    assert len(readings) == 2
    assert readings[0].metric == "uptime"
    assert readings[0].value == 99.2


def test_parse_skips_bad_rows():
    raw = '[{"metric":"uptime","value":99.2,"unit":"percent"},{"broken":true}]'
    readings = parse_logs_from_json(raw)
    assert len(readings) == 1
    assert readings[0].metric == "uptime"


def test_parse_empty_array():
    readings = parse_logs_from_json("[]")
    assert readings == []


def test_parse_with_optional_period():
    raw = '[{"metric":"uptime","value":99.9,"unit":"percent","period":"2026-05"}]'
    readings = parse_logs_from_json(raw)
    assert readings[0].period == "2026-05"
