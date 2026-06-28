from langchain_core.tools import tool

_MOCK_VENDOR_DB = {
    "delivery_time": {"metric": "delivery_time", "value": 60.0, "unit": "hours", "period": "2026-05"},
}


@tool
def lookup_vendor_metric(metric: str) -> dict:
    """Look up a missing operational metric for the vendor by name.

    Use this when the provided logs are missing a metric the contract requires.
    Returns the reading dict, or a 'not_found' marker.
    """
    if metric in _MOCK_VENDOR_DB:
        return _MOCK_VENDOR_DB[metric]
    return {"metric": metric, "value": None, "unit": "unknown", "not_found": True}
