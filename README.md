# HomeCue

A connected home-support prototype with a FastAPI website and API, a Flutter caregiver app, and ESP32 firmware. The website and app share accounts, home settings, activity, and demo purchases through one backend.

## What it includes

- Account registration, login, and locally issued one-time password recovery.
- Home setup, caregiver access, module preferences, and observation history.
- Starter, Family, and configurable Custom packages with live prices.
- Demo UPI, card, and EMI checkout; purchased plans determine available options.
- Authenticated ESP32 observations and heartbeat reporting.
- An optional email-allowlisted, password-protected HTTPS gateway for remote browser access.

Payments are simulated. Planned hardware features remain prototypes; this is not a medical device or emergency-monitoring service.

## Run the website and API

Use Python 3.12 or newer. On macOS:

```sh
zsh scripts/START_BACKEND_MAC.command
```

Or set up the backend manually:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

On Windows, run `scripts/START_BACKEND_WINDOWS.ps1`, or follow [the Windows setup guide](README_START_HERE.md).

Open <http://127.0.0.1:8000/>. Create an account with a password of at least 12 characters, create a home, and complete a demo purchase to unlock its included settings. The backend creates its local SQLite database and development signing secret on first start. Neither is included in Git.

## Build the caregiver app

Install a current stable Flutter SDK. The browser build is served by the same backend:

```sh
cd mobile_flutter
flutter pub get
flutter build web --base-href /app/ --no-web-resources-cdn
```

Start the backend and open <http://127.0.0.1:8000/app/>. Sign in with the same account as the website. Generated build files are excluded from the repository, so build the app after cloning.

For Android, install the Android SDK, connect an emulator or device, and run `flutter run` from `mobile_flutter`. Android compilation and physical-device operation have not been verified here. See [the app guide](mobile_flutter/README.md) for server settings and networking.

## Demo custom pricing

Custom prices are calibrated to the fixed plans: Task guidance plus Orientation with one zone and one caregiver matches Starter at ₹14,999 setup + ₹499/month. All five options with three zones and three caregivers match Family at ₹24,999 setup + ₹999/month.

| Item | Setup | Monthly service |
| --- | ---: | ---: |
| Base package, including one zone and one caregiver | ₹4,999 | ₹199 |
| Task guidance | ₹5,000 | ₹150 |
| Movement awareness | ₹2,000 | ₹100 |
| Entrance awareness | ₹2,000 | ₹100 |
| Orientation and routines | ₹5,000 | ₹150 |
| Family updates | ₹2,000 | ₹100 |
| Each additional zone or caregiver | ₹1,000 | ₹50 |

Annual service gets a 15% discount, using the rounded discounted monthly rate multiplied by 12. The initial demo payment includes setup plus the first billing period. The API calculates the saved total from the selected options; no real payment is processed.

## ESP32 firmware

Open `esp32_firmware` with PlatformIO. Copy `include/secrets.example.h` to `include/secrets.h`, then fill in your Wi-Fi settings, backend address, home ID, and device token. Keep the real file out of version control. Read [the wiring and safety guide](esp32_firmware/WIRING_AND_SAFETY.md) before connecting hardware.

## Remote access

Localhost and LAN addresses do not work from other networks. For temporary HTTPS access, install `cloudflared` and run:

```sh
zsh scripts/START_REMOTE_ACCESS_MAC.command
```

Enter an approved, existing HomeCue account email. The launcher serves the password-protected gateway on loopback port 8001 and tunnels that gateway. Visitors use their HomeCue password; private pages and API data remain behind sign-in. Keep the Mac awake and online. A temporary tunnel gets a new address when restarted. See [remote-access details](docs/REMOTE_ACCESS.md).

GitHub stores the source code; pushing this repository does not deploy the Python server or make the app available continuously.

## Verification

```sh
python3 -m pip install -r backend/requirements-dev.txt
python3 -m pytest backend/tests -q
```

```sh
cd mobile_flutter
flutter analyze
flutter test
```

Optional browser checks live in `scripts/`. They use throwaway databases. Most expect Chrome on macOS; `browser_smoke_test.py` also accepts `HOMECUE_BROWSER_PATH`.

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/` | FastAPI, local database models, authentication, plans, remote gateway, tests, and website assets |
| `mobile_flutter/` | Flutter app with Android and browser platform files |
| `esp32_firmware/` | PlatformIO firmware and example device configuration |
| `scripts/` | Startup, build, simulation, and browser verification scripts |
| `docs/` | Architecture, limitations, and remote-access guidance |

Local database records, signing secrets, credentials, build outputs, virtual environments, temporary remote addresses, and generated screenshots are excluded from version control.
