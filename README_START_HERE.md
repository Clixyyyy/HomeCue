# HomeCue — Full connected prototype (v0.3)

**Goal:** A VS Code project connecting the photographed ESP32 + RC522 RFID (and optional PIR/RTC/audio) to a private local backend, black/white website and Flutter caregiver mobile app.

**Files inside:** `backend/` (actual API + working web UI), `mobile_flutter/` (Flutter source), `esp32_firmware/` (PlatformIO firmware), `scripts/`, `docs/`.

**What is implemented:** Account login, new home, five module preferences, trusted contacts, grant registered caregiver access, owner-generated one-time device token, authorised ESP32 heartbeat and observation events, event history, acknowledge and demo labels, pricing proposals, website and Flutter clients using the same API. Backend integration tests pass. Physical hardware behaviour is not verified yet. There are NO real alerts (SMS/push), actual lighting automation, actual navigation or payment checkout.

## Phase A — Run the website + API in VS Code (Windows)

**Mac:** Double-click `scripts/START_BACKEND_MAC.command`, or run `zsh scripts/START_BACKEND_MAC.command` from the project root. Open http://127.0.0.1:8000. Keep the terminal open while using HomeCue; press Ctrl+C to stop it.

1. Extract ZIP. Open **`HomeCue_Integrated_Build`** as the folder in VS Code.
2. Install Python 3.12 or 3.13, VS Code Python extension.
3. Open terminal (`Ctrl + backtick`) and enter:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Alternatively run `powershell -ExecutionPolicy Bypass -File .\scripts\START_BACKEND_WINDOWS.ps1` from the project root.

4. Browser: **http://127.0.0.1:8000** (website) and **http://127.0.0.1:8000/docs** (interactive API docs).
5. Open My Home → Create account → enter email and **12+ character password** → Create your family home.
6. Home setup → adjust `Task guidance` preference. This stores a setting; it doesn't yet remotely control hardware.
7. Activity → `Add demo event`. Its label says DEMO, not real sensor data.
8. Home setup → **Generate / rotate device token**; copy the value once. If you regenerate it, the old ESP32 token stops working.

**Note:** When server starts locally, it creates `backend/storage/homecue.db` and a development secret. Don't upload either to public GitHub. Do not open the dev server to the internet.

## Phase B — Connect the Android Flutter app to the SAME server

1. Install Flutter SDK + Android SDK and VS Code Flutter/Dart extensions; run `flutter doctor`.
2. From the project root, run PowerShell script `powershell -ExecutionPolicy Bypass -File .\scripts\PREPARE_FLUTTER_WINDOWS.ps1`, or do these steps manually:

```powershell
flutter create --platforms=android homecue_flutter_app
Copy-Item .\mobile_flutter\lib\main.dart .\homecue_flutter_app\lib\main.dart -Force
Copy-Item .\mobile_flutter\pubspec.yaml .\homecue_flutter_app\pubspec.yaml -Force
cd homecue_flutter_app
flutter pub get
```

3. **Before running Android** add Internet permission and debug-only HTTP access as described in `mobile_flutter/README.md`.
4. For Android emulator, use the default `http://10.0.2.2:8000`, with FastAPI on your PC.
5. For an actual Android phone, both devices must be on the same trusted Wi-Fi. On the PC run `ipconfig`, find the PC IPv4 e.g. `192.168.1.12`, then start backend with:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

6. On Android tap ⚙ settings and enter `http://192.168.1.12:8000` using your actual PC IP. Allow TCP port 8000 only on Windows **Private** network firewall, not Public. A phone using cellular or isolated guest Wi-Fi cannot reach the local server.
7. `flutter run` from the `homecue_flutter_app` folder, or F5 with the phone selected in VS Code.
8. Log in using the **same email and password** you used on the website. Events and saved preferences will match after refresh.

**Security:** Plain HTTP is for a local trusted lab network only. Do not use with real family/patient information until HTTPS and full security checks are implemented.

## Phase C — Test the server-to-website-to-app connection WITHOUT hardware

In a second terminal at project root, use the token from Home Setup. Example PowerShell commands:

```powershell
$env:HC_SERVER_URL = 'http://127.0.0.1:8000'
$env:HC_HOME_ID = '1'                # change to your real home ID from /docs or dashboard API
$env:HC_DEVICE_TOKEN = 'YOUR-ONE-TIME-DEVICE-TOKEN'
py -3 .\scripts\simulate_esp32_event.py
```

Activity on BOTH website and Flutter should show `TEST ONLY: script sent a simulated RFID observation`, with DEVICE source. This proves that **event ingestion + account access + cross-client reads** work locally. It does NOT prove a sensor was read.

## Phase D — Upload firmware to the ESP32

1. Install VS Code **PlatformIO IDE** extension. Open `esp32_firmware` as its own project.
2. Copy `esp32_firmware/include/secrets.example.h` to `esp32_firmware/include/secrets.h`.
3. Fill Wi-Fi network, PC LAN IPv4 URL, actual `HOMECUE_HOME_ID`, and device token. Keep token secret; `secrets.h` is in `.gitignore`.
4. **First** connect only ESP32 over the right USB data cable. Build and upload, open PlatformIO Serial Monitor at 115200 baud.
5. **Disconnect USB power** before adding the RC522 reader. Follow `esp32_firmware/WIRING_AND_SAFETY.md`; RC522 needs 3.3V, and its white tags must be 13.56 MHz compatible.
6. Reconnect and scan the blue fob or card. A UID should print to Serial Monitor; if Wi-Fi/server/token all work, its `tag_scan` event shows in website and mobile Activity.
7. Optional: wire verified PIR board, use `ENABLE_PIR_SENSOR true`; see precise voltage warnings in the wiring guide.
8. Optional: RTC + DFPlayer audio only after separate hardware verification and an appropriate **≤32GB FAT32** microSD. The 64GB card in your photos is not manufacturer-supported by the DFPlayer Mini.

### Important limitations

* Only **one ESP32 board** and one RC522 reader were confirmed in your photos. This project **does not require a Raspberry Pi** for the first prototype.
* Movement sensor labeling and power supply specifications were unclear in the photographs; **do not connect uncertain board pins or mains supply until confirmed**.
* The microSD 64GB works differently across devices; do not assume it works with DFPlayer Mini.
* No ESP32 or Android hardware compilation was possible in this environment (no PlatformIO or Flutter SDK). **Backend API tests passed**. Browser render testing was blocked by the test environment's browser network policy; JS syntax check passed.
* No real patient data, medical decisions, emergency monitoring or unvalidated unattended use.

## Development test status

`cd backend` → `python -m pytest -q` if `pytest` and `httpx` are installed. Tests include registration/login, ownership isolation, home creation, module saving, device token rotation, heartbeat, event upload, acknowledgement and viewer-only access. The integrated project source is included so you can run these tests on your PC.

## Figma reference

Your editable Nike-style monochrome HomeCue Figma UI: https://www.figma.com/design/Rcq8OpZPZbNWTYTjvAbXkN

Figma is the design reference, not the backend runtime. This website and mobile app implement matching high-contrast black/white screens and connect directly to one shared FastAPI API.

## Purchased-plan dashboard

Successful demo checkout now requires an account and records the plan for the home. My Home shows the purchased plan, date, included options, home zones and caregiver account allowance. Starter includes task guidance and orientation; Family includes all five options; Custom Complete includes the selected options. Options outside the purchased plan are locked in Setup and rejected by the API. No real charges are processed. Refresh the website or wait up to 10 seconds in the app to see a purchase made in the other client. Earlier demo checkouts were not saved; complete a new demo checkout to record a plan.
