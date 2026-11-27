"""Константи інтеграції «Комора»."""
from __future__ import annotations

DOMAIN = "komora"

CONF_URL = "url"
CONF_TOKEN = "token"
CONF_PANEL = "panel"
CONF_HORIZON = "horizon_days"
CONF_WITHIN = "within_days"

DEFAULT_HORIZON = 7
DEFAULT_WITHIN = 2
PANEL_PATH = "komora"

# SSE: які зміни зачіпають те, що показує інтеграція
REFRESH_TOPICS = {"stock", "items", "shopping", "all"}

ATTR_QUERY = "query"
ATTR_LIMIT = "limit"
ATTR_ITEM = "item"
ATTR_QTY = "qty"
ATTR_UNIT = "unit"
ATTR_REASON = "reason"
ATTR_NOTE = "note"
ATTR_ENTRY = "config_entry_id"

REASONS = ["cooking", "used", "spoiled", "discarded", "given", "lost", "other"]
