import json
from pathlib import Path
from app.models import MetricReading


def parse_logs_from_json(raw: str | bytes) -> list[MetricReading]:
    """Parse a JSON array of vendor metrics into validated MetricReading objects.

    Defensive: skips malformed rows instead of crashing the whole audit.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)

    readings: list[MetricReading] = []
    for i, row in enumerate(data):
        try:
            readings.append(MetricReading(**row))
        except Exception as e:  # noqa: BLE001 — log and continue, don't die
            print(f"[parsing] skipped row {i}: {e}")
    return readings


def load_logs_file(path: str | Path) -> list[MetricReading]:
    return parse_logs_from_json(Path(path).read_text(encoding="utf-8"))
