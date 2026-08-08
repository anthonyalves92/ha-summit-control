"""Constants for the Summit Control (Sierra) integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "summit_control"

# Sierra platform hosts (reverse-engineered + confirmed live).
IDENTITY_BASE: Final = "https://ip-lib.summitcontrol.com:4000"   # /login, /refresh-token
API_BASE: Final = "https://sierra-lib.summitcontrol.com:3000"    # /v1/... REST API

# Endpoints (paths under API_BASE).
EP_SHELL_BY_USER: Final = "/v1/shell/get_by_user"
EP_GROUP_PERMISSIONS: Final = "/v1/user_group_permission/get/all"
EP_DEVICES_BY_IDS: Final = "/v1/device/get/ids"
EP_RESOURCES_BY_IDS: Final = "/v1/device_resource/get/all_by_ids"
EP_COMMAND: Final = "/v1/command/"  # + action, e.g. "open"

REQUEST_TIMEOUT: Final = 30
# The access token is a JWT with a ~120 s lifetime; refresh this many seconds early.
TOKEN_REFRESH_MARGIN: Final = 30
DEFAULT_TOKEN_TTL: Final = 110

# Gates rarely change and there is no live open/closed state to poll, so the
# coordinator polls slowly — mainly to keep auth warm and pick up gate changes.
DEFAULT_SCAN_INTERVAL: Final = 300
MIN_SCAN_INTERVAL: Final = 60

MANUFACTURER: Final = "Security Brands, Inc."
