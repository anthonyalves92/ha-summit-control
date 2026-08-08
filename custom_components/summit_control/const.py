"""Constants for the Summit Control integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "summit_control"

# --- Cloud API (Security Brands "SnapApi", recovered from the official app) ---
BASE_URL: Final = "https://summitcontrol.com/SnapApi/index.php/"
# Match the official app's client string; some hosting front-ends are picky about UA.
USER_AGENT: Final = "okhttp/3.12.1"

EP_LOGIN: Final = "auth/login"
EP_LOGOUT: Final = "auth/logout"
EP_DASHBOARD: Final = "user/dashboard"
EP_ACTIONS_OPEN: Final = "Actions/Open"
EP_LATCH_OPEN: Final = "Latch/Open"
EP_LATCH_CLOSE: Final = "Latch/Close"
EP_RELAY_STATUS: Final = "Actions/RelayStatus"

GRANT_TYPE: Final = "client_credentials"
REQUEST_TIMEOUT: Final = 30  # seconds

# --- Options ---
CONF_COMMAND_MODE: Final = "command_mode"
MODE_AUTO: Final = "auto"          # detect from reported relay status
MODE_LATCH: Final = "latch"        # maintained relay: Latch/Open + Latch/Close, real state
MODE_MOMENTARY: Final = "momentary"  # single pulse: Actions/Open, optimistic state
COMMAND_MODES: Final = [MODE_AUTO, MODE_LATCH, MODE_MOMENTARY]

DEFAULT_SCAN_INTERVAL: Final = 30    # seconds
MIN_SCAN_INTERVAL: Final = 10

# Token is refreshed this many seconds before its stated expiry.
TOKEN_EXPIRY_MARGIN: Final = 60

# Relay status string values seen in the app (case-insensitive match).
RELAY_OPEN_VALUES: Final = frozenset({"on", "open", "1", "opened", "unlatched"})
RELAY_CLOSED_VALUES: Final = frozenset({"off", "close", "closed", "0", "latched"})
