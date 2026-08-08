# Summit Control — Home Assistant integration

Home Assistant control of a **Security Brands "Summit Control" / Ascent** cellular gate/access controller, using the same cloud API as the official app (`com.snaplock.mobility.summitcontrol`).

> **Cloud, not local.** These units are cellular and have **no LAN API** — the app, the unit, and this integration all talk to `summitcontrol.com`. There is no local path; this integration is the cloud path with proper TLS verification, token handling, and polling.

Use with your own account and gate only.

---

## What you get

- **Config flow** (UI) — username + password, no YAML.
- One **`cover` entity per relay** on each gate (`device_class: gate`), with **open/close**.
- **OAuth2 token handling** with automatic renewal (the server issues only `client_credentials` tokens, so renewal = re-login with your stored credentials — handled for you, including on 401).
- **`DataUpdateCoordinator`** polling `user/dashboard` for state (default 30 s).
- Reauth flow if your password changes.

## Two gate modes (auto-detected)

Summit units expose relays in one of two ways; the integration figures out which from the reported relay status, and you can override it in **Settings → Devices & Services → Summit Control → Configure → Command mode**:

| Mode | Open → | Close → | State |
|---|---|---|---|
| **latch** (maintained relay) | `Latch/Open` | `Latch/Close` | Real, from `relay1_status`/`relay2_status` |
| **momentary** (single control line) | `Actions/Open` pulse | `Actions/Open` pulse | Optimistic (`assumed_state`) |
| **auto** (default) | picks latch if the unit reports a usable relay state, else momentary | | |

If your gate is a momentary operator (one button that opens/toggles), both open and close send the same pulse — that's all the hardware offers, and HA marks the entity as assumed-state.

---

## Install

### Option A — HACS (custom repository)
1. HACS → ⋮ → **Custom repositories** → add this repo's URL, category **Integration**.
2. Install **Summit Control**, then restart Home Assistant.

### Option B — Manual
Copy `custom_components/summit_control/` into your HA `config/custom_components/` directory and restart.

### Configure
**Settings → Devices & Services → Add Integration → Summit Control**, then enter your Summit Control app username and password. On submit it logs in and lists your gate(s). Then open the gate once from the new cover entity to confirm it actuates.

---

## Validate / troubleshoot outside HA

`validate_summit.py` exercises the same API this integration uses, with no HA and no dependencies:

```bash
python3 validate_summit.py            # login + list devices (read-only)
python3 validate_summit.py --open     # also fire Actions/Open (moves the gate; asks first)
python3 validate_summit.py --latch-open   # maintained relay ON
python3 validate_summit.py --latch-close  # maintained relay OFF
```
Credentials come from a prompt or `SUMMIT_USER` / `SUMMIT_PASS` env vars. Use it to confirm your gate moves and to see whether it reports real `relay1_status`/`relay2_status` (→ latch mode) or not (→ momentary).

---

## Limitations & notes

- **Cloud-dependent:** if `summitcontrol.com` or your cellular link is down, control is unavailable. Polling defaults to 30 s (configurable, min 10 s); cellular check-ins are not instant, so state can lag a command by a few seconds.
- **No stop:** the API exposes no stop command, so the cover doesn't advertise one.
- **Platform migration:** Security Brands is rolling out a newer **"Sierra"** platform (`com.summitcontrol` app, `sierra.summitcontrol.com`). If your unit is migrated, this legacy API integration will need to be re-pointed at the newer backend.
- This integration verifies TLS certificates normally.

## How it works (API summary)

Base `https://summitcontrol.com/SnapApi/index.php/`. Login `POST auth/login` (`client_credentials`, username→`client_id`, password→`client_secret`) → `Bearer` token. Commands `POST Actions/Open` / `Latch/Open` / `Latch/Close` with `{deviceID, deviceCode, relay}`. State from `GET user/dashboard`.

## Disclaimer

Unofficial; not affiliated with or endorsed by Security Brands, Inc. "Summit Control" and "Ascent" are the vendor's marks. Provided as-is for interoperability with hardware you own; the vendor may change the API at any time.

## License

MIT — see [LICENSE](LICENSE).
