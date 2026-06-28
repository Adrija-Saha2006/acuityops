from langchain_core.tools import tool

# Simulates a vendor metrics API / internal monitoring DB.
# During the July 30 2024 us-east-1 Kinesis incident, individual EC2 instances
# also experienced connectivity loss for portions of the 7-hour window.
# Instance-level uptime measured across the fleet: 99.2% (below the 99.5% SLA).
_MOCK_VENDOR_DB = {
    "instance_uptime": {
        "metric": "instance_uptime",
        "value": 99.2,
        "unit": "percent",
        "period": "2024-07",
        "notes": "us-east-1 fleet average — Jul 30 2024 Kinesis incident",
    },
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
