#!/usr/bin/env python3
"""
Summit Control (Sierra) — live check / gate discovery.

Confirms the Sierra API works with YOUR account and lists the gates you're
allowed to open. Talks to the same cloud as the "SummitControl Sierra" app.

No third-party packages (Python 3.8+ stdlib only).

Credentials: set SUMMIT_USER / SUMMIT_PASS, or you'll be prompted. The password
is read with getpass and never echoed or stored.

Usage:
  python3 validate_summit.py            # login + list gates (read-only)
  python3 validate_summit.py --open N   # open gate #N from the list (MOVES IT; asks first)
"""
import argparse
import getpass
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request

IDENT = "https://ip-lib.summitcontrol.com:4000"
API = "https://sierra-lib.summitcontrol.com:3000"


def _opener():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def _post(op, base, path, body, token=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["access_token"] = token
    req = urllib.request.Request(
        base + path, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with op.open(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _as_list(d):
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)]
    return [d] if isinstance(d, dict) else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", type=int, metavar="N", help="open gate #N from the list")
    a = ap.parse_args()

    user = os.environ.get("SUMMIT_USER") or input("Summit Control username: ").strip()
    password = os.environ.get("SUMMIT_PASS") or getpass.getpass("Summit Control password: ")

    op = _opener()
    print("\n== Logging in ==")
    st, raw = _post(op, IDENT, "/login", {"username": user, "password": password})
    if st != 200:
        print(f"LOGIN FAILED (HTTP {st}): {raw[:300]}")
        sys.exit(1)
    msg = json.loads(raw)["message"]
    token, uid = msg["access_token"], msg["user"]["_id"]
    print(f"  OK  user={msg['user'].get('username')}")

    # Discover gates: shell -> user_group permissions -> device/resource names.
    shells = json.loads(_post(op, API, "/v1/shell/get_by_user", {"user_id": uid}, token)[1])
    gids = {s.get("user_group_id") for s in _as_list(shells) if s.get("user_group_id")}
    pairs = []
    for gid in gids:
        perms = json.loads(_post(op, API, "/v1/user_group_permission/get/all", {"user_group_id": gid}, token)[1])
        for perm in _as_list(perms):
            did = perm.get("device_id")
            if not did or not (perm.get("actions") or {}).get("open"):
                continue
            for relay in perm.get("relays") or []:
                rid = relay.get("resource_id")
                if rid:
                    pairs.append((did, rid))
    seen = set()
    pairs = [x for x in pairs if not (x in seen or seen.add(x))]

    device_ids = list({d for d, _ in pairs})
    resource_ids = [r for _, r in pairs]
    devs = {d["_id"]: d for d in _as_list(json.loads(_post(op, API, "/v1/device/get/ids", {"device_ids": device_ids}, token)[1])) if d.get("_id")}
    ress = {d["_id"]: d for d in _as_list(json.loads(_post(op, API, "/v1/device_resource/get/all_by_ids", {"resource_ids": resource_ids}, token)[1])) if d.get("_id")}

    print(f"\n== {len(pairs)} gate(s) you can open ==")
    for i, (did, rid) in enumerate(pairs):
        print(f"  [{i}] {ress.get(rid, {}).get('name', 'Gate')}  (device: {devs.get(did, {}).get('name', '?')})")

    if a.open is not None:
        if not (0 <= a.open < len(pairs)):
            print(f"\nNo gate #{a.open}."); sys.exit(1)
        did, rid = pairs[a.open]
        name = ress.get(rid, {}).get("name", "Gate")
        print(f"\n*** This will OPEN the real gate: {name}")
        if input("Type YES to proceed: ").strip() != "YES":
            print("Aborted."); sys.exit(0)
        st, raw = _post(op, API, "/v1/command/open", {"device": did, "resource": rid, "user": uid}, token)
        print(f"  command/open -> HTTP {st}  {raw[:200]}")


if __name__ == "__main__":
    main()
