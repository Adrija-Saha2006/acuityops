from langchain_core.tools import tool

# Mock vendor metrics database.
# In production this would call real vendor APIs / monitoring systems.
# Values are set slightly below typical SLA thresholds so the gather cycle
# produces meaningful violations for any contract type in a demo.
_MOCK_VENDOR_DB = {
    # AWS — July 2024 Kinesis incident
    "instance_uptime":      {"metric": "instance_uptime",      "value": 99.2,  "unit": "percent", "period": "2024-07"},
    # Google Cloud
    "gcp_uptime":           {"metric": "gcp_uptime",           "value": 99.4,  "unit": "percent", "period": "2024-06"},
    "gcp_sql_uptime":       {"metric": "gcp_sql_uptime",       "value": 99.6,  "unit": "percent", "period": "2024-06"},
    # Azure
    "azure_vm_uptime":      {"metric": "azure_vm_uptime",      "value": 99.7,  "unit": "percent", "period": "2024-09"},
    "azure_storage_uptime": {"metric": "azure_storage_uptime", "value": 99.8,  "unit": "percent", "period": "2024-09"},
    # Generic cloud / SaaS
    "uptime":               {"metric": "uptime",               "value": 99.5,  "unit": "percent", "period": "2026-05"},
    "api_uptime":           {"metric": "api_uptime",           "value": 99.85, "unit": "percent", "period": "2026-05"},
    "api_error_rate":       {"metric": "api_error_rate",       "value": 0.8,   "unit": "percent", "period": "2026-05"},
    # Support SLA
    "response_time":        {"metric": "response_time",        "value": 3.2,   "unit": "hours",   "period": "2026-05"},
    "resolution_time":      {"metric": "resolution_time",      "value": 6.5,   "unit": "hours",   "period": "2026-05"},
    # Logistics / delivery
    "delivery_time":        {"metric": "delivery_time",        "value": 60.0,  "unit": "hours",   "period": "2026-05"},
    # Telecom
    "packet_loss":          {"metric": "packet_loss",          "value": 0.15,  "unit": "percent", "period": "2026-05"},
    "latency":              {"metric": "latency",              "value": 45.0,  "unit": "ms",      "period": "2026-05"},
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
