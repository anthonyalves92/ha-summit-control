#!/usr/bin/env python3
"""
Summit Control — Phase 1 live replay / validation.

Purpose: confirm the recovered API works with YOUR account and gate, and harvest
the deviceID / deviceCode / relay layout the Home Assistant integration needs.
Talks to the same cloud (summitcontrol.com/SnapApi) as the official app.

No third-party packages required (Python 3.8+ stdlib only).

Credentials: set env vars SUMMIT_USER / SUMMIT_PASS, or you'll be prompted.
The password is read with getpass and never echoed or stored.

Usage:
  python3 validate_summit.py                 # login + list devices (safe, read-only)
  python3 validate_summit.py --open          # + fire Actions/Open (MOVES THE GATE; asks first)
  python3 validate_summit.py --latch-open    # + Latch/Open  (maintained relay ON)
  python3 validate_summit.py --latch-close   # + Latch/Close (maintained relay OFF)
      [--device N] [--relay 1|2] [--show-token]
"""
import argparse, getpass, json, os, sys, urllib.request, urllib.error

BASE = "https://summitcontrol.com/SnapApi/index.php/"
UA = "okhttp/3.12.1"  # match the app's client string


def _req(method, path, token=None, body=None, timeout=30):
    url = BASE + path
    data = None
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json;charset=UTF-8"
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, "ERROR: %s" % e


def _json(raw):
    try:
        return json.loads(raw)
    except Exception:
        return None


def login(user, password):
    code, raw = _req("POST", "auth/login", body={
        "client_id": user, "client_secret": password, "grant_type": "client_credentials"})
    j = _json(raw) or {}
    if code == 200 and j.get("access_token"):
        return j
    print("LOGIN FAILED (HTTP %s): %s" % (code, raw[:400]))
    sys.exit(1)


def flatten_devices(dash):
    """Return a flat list of device dicts from user/dashboard."""
    out = []
    data = (dash or {}).get("data") or {}
    for grp in data.get("devices") or []:
        addr = grp.get("address")
        for d in grp.get("deviceDetails") or []:
            d = dict(d)
            d["_address"] = addr
            out.append(d)
    return out


def show_devices(devs):
    if not devs:
        print("  (no devices returned)")
        return
    for i, d in enumerate(devs):
        did = d.get("deviceID") or d.get("ID") or "?"
        dcode = d.get("deviceCode") or d.get("device_code") or "?"
        print("  [%d] %s / %s" % (i, d.get("product_name", "?"), d.get("location_name") or d.get("_address") or ""))
        print("      deviceID=%s  deviceCode=%s" % (did, dcode))
        print("      relay1_status=%s  relay2_status=%s  last_checkin=%s" % (
            d.get("relay1_status"), d.get("relay2_status"), d.get("last_checkin")))


def pick(devs, idx):
    if not devs:
        print("No devices to act on."); sys.exit(1)
    if idx is None:
        if len(devs) == 1:
            return devs[0]
        idx = int(input("Which device index? "))
    return devs[idx]


def confirm(action, d, relay):
    did = d.get("deviceID") or d.get("ID")
    print("\n*** This will send %s to the REAL gate:" % action)
    print("      %s / %s  deviceID=%s relay=%s" % (d.get("product_name"), d.get("location_name"), did, relay))
    if input("Type YES to proceed: ").strip() != "YES":
        print("Aborted."); sys.exit(0)


def act(path, token, d, relay):
    body = {"deviceID": d.get("deviceID") or d.get("ID"),
            "deviceCode": d.get("deviceCode") or d.get("device_code"),
            "relay": str(relay)}
    code, raw = _req("POST", path, token=token, body=body)
    print("  %s -> HTTP %s  %s" % (path, code, raw[:300]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true", help="fire Actions/Open (momentary)")
    ap.add_argument("--latch-open", action="store_true")
    ap.add_argument("--latch-close", action="store_true")
    ap.add_argument("--device", type=int, default=None)
    ap.add_argument("--relay", default="1")
    ap.add_argument("--show-token", action="store_true")
    a = ap.parse_args()

    user = os.environ.get("SUMMIT_USER") or input("Summit Control username: ").strip()
    password = os.environ.get("SUMMIT_PASS") or getpass.getpass("Summit Control password: ")

    print("\n== Logging in (client_credentials) ==")
    tok = login(user, password)
    at = tok["access_token"]
    shown = at if a.show_token else (at[:8] + "…" + at[-4:])
    print("  OK  token_type=%s expires_in=%s scope=%s" % (tok.get("token_type"), tok.get("expires_in"), tok.get("scope")))
    print("  access_token=%s" % shown)

    print("\n== GET user/dashboard ==")
    code, raw = _req("GET", "user/dashboard", token=at)
    dash = _json(raw)
    if code != 200 or dash is None:
        print("  dashboard HTTP %s: %s" % (code, raw[:400])); sys.exit(1)
    devs = flatten_devices(dash)
    print("  %d device(s):" % len(devs))
    show_devices(devs)

    if a.open:
        d = pick(devs, a.device); confirm("Actions/Open (momentary pulse)", d, a.relay)
        act("Actions/Open", at, d, a.relay)
    elif a.latch_open:
        d = pick(devs, a.device); confirm("Latch/Open (relay ON)", d, a.relay)
        act("Latch/Open", at, d, a.relay)
    elif a.latch_close:
        d = pick(devs, a.device); confirm("Latch/Close (relay OFF)", d, a.relay)
        act("Latch/Close", at, d, a.relay)
    else:
        print("\n(read-only run — pass --open / --latch-open / --latch-close to actuate)")

    print("\nDone. For the integration I need, from above: each gate's deviceID, deviceCode,")
    print("its product_name, and whether relay1_status/relay2_status show real values.")


if __name__ == "__main__":
    main()
