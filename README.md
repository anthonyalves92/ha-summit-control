# Summit Control — Home Assistant integration

Home Assistant control of **Security Brands "Summit Control" (Sierra platform)** gates — the cellular access controllers used by many communities/HOAs. Lets you open the gates your account is permitted to open, from Home Assistant, using the same cloud API as the "SummitControl Sierra" app.

> **Cloud only.** These controllers are cellular and have no local API; the app, the unit, and this integration all talk to `summitcontrol.com`. This integration is that cloud path done cleanly (proper TLS, token refresh, polling).

Use with your own account only.

---

## What you get

- **Config flow** (UI) — sign in with your Summit Control username + password. No YAML.
- One **`cover` entity per gate** you're allowed to open (`device_class: gate`), e.g. *Main Gate Entry*, *Ramp Gate*.
- **Automatic session handling** — the Sierra access token is very short-lived (~2 minutes); the integration refreshes it for you.
- Your gates are **discovered automatically** from your account permissions — nothing to configure by hand.

## How gates behave

Residents get a **momentary open** command (there's no latch/hold and no live open/closed feedback from the cloud), so each gate is modeled as an **open-only, assumed-state** cover: pressing **Open** fires the gate relay; the operator closes it on its own. Home Assistant marks the entity assumed-state because the cloud doesn't report gate position.

---

## Install

### Option A — HACS (custom repository)
1. HACS → ⋮ → **Custom repositories** → add this repo's URL, category **Integration**.
2. Install **Summit Control**, then restart Home Assistant.

### Option B — Manual
Copy `custom_components/summit_control/` into your HA `config/custom_components/` directory and restart.

### Configure
**Settings → Devices & Services → Add Integration → Summit Control**, then enter your Summit Control username and password. Your gates appear automatically as cover entities.

---

## Validate / troubleshoot outside HA

`validate_summit.py` exercises the same API the integration uses, with no HA and no dependencies:

```bash
python3 validate_summit.py            # login + list the gates you can open (read-only)
python3 validate_summit.py --open N   # open gate #N from the list (asks for confirmation first)
```
Credentials come from a prompt or the `SUMMIT_USER` / `SUMMIT_PASS` env vars.

---

## Limitations & notes

- **Cloud-dependent:** if the Summit Control cloud or your cellular gate is offline, control is unavailable.
- **No live state:** the cloud doesn't report whether a gate is open or closed for a resident, so the entities are assumed-state, open-only.
- **Momentary open only:** matches what the app offers residents (no latch/hold).
- Two Summit Control generations exist — a legacy platform and this newer **Sierra** platform. This integration targets **Sierra** (`sierra.summitcontrol.com`). If you can't sign in, confirm you use the "SummitControl Sierra" app / `sierra.summitcontrol.com`.
- This integration verifies TLS certificates normally.

## How it works (API summary)

Auth: `POST ip-lib.summitcontrol.com:4000/login {username, password}` → short-lived access token (refreshed via `/refresh-token`), attached to REST calls as an `access_token` header. Gate discovery walks your access record (shell → user-group permissions → device/relay resources) on `sierra-lib.summitcontrol.com:3000/v1/`. Open: `POST /v1/command/open {device, resource, user}`. Your account/device identifiers are fetched at runtime — none are stored in this code.

## Disclaimer

Unofficial; not affiliated with or endorsed by Security Brands, Inc. Provided as-is for interoperability with a service you have an account on; the vendor may change the API at any time.

## License

MIT — see [LICENSE](LICENSE).
