# HomeCue: actual prototype architecture

```
[Physical 13.56MHz tag]--RC522--> [ESP32]
[Motion, if sensor verified]--PIR--> [ESP32]--local Wi-Fi HTTP/JSON--> [FastAPI on PC]
[DS3231 time, optional] -----------------/                                  |
[DFPlayer prompt, optional] <--- local rule                                  v
                                                                       [SQLite DB]
                                                                        /      \
                                                                     Web      Flutter
                                                                 caregiver   caregiver
                                                                  dashboard    app
```

**Physical task proof of concept:** An RFID tag must come within reader range. The ESP32 prints a UID on Serial Monitor, sends a limited event, and can optionally play a pre-recorded prompt for a configured tag. It does NOT detect what someone is doing across the room. A scan is not proof a task was completed.

**Movement proof of concept:** An optional PIR reports a change in motion status. It cannot identify a person, confirm bathroom arrival, detect still presence, or ensure safety. Night-navigation floor light and entrance reed sensors are NOT included in the photographed inventory.

**Backend:** FastAPI + SQLAlchemy + SQLite. Registered caregivers have their own login. The owner can add an existing user to a home as viewer/editor; owner issues separate one-time device token. The app/browser uses user JWT, while ESP32 uses only the device token. Tokens are not interchangeable.

**Event schema:** `{ "module":"task", "kind":"tag_scan", "message":"Compatible tag scanned at task station" }`.  The server stores `source = device`, a UTC timestamp, and an acknowledgement flag. Device `heartbeat` marks the board recently online; it does **not** mean sensor readings are medically reliable.

**Mobile app:** Flutter `http` sends authenticated calls to the same `/api` URLs as the website. No separate mobile database; local app only securely caches session token and server address. For the Android emulator, point at `10.0.2.2:8000`; physical Android phone must use the PC's LAN IPv4 address over trusted Wi-Fi. Device token never enters the app.

**Figma:** Visual design files are editable UI references. Website and app implement matching black/white styling, but Figma itself is not a live server or data-binding runtime. Edits in Figma do not automatically update website or Flutter source.

**Privacy:** Do not enter medical histories. User contact numbers are only local lab test data. Hardware records omit RFID UID from the server message; UIDs print only to serial for configuration. No cloud telemetry without an explicit secure deployment.

**Safety:** Never connect an exposed metal mains PSU directly for a desk prototype. No automatic locking, gas/stove actions, or medicine control. Only bench-test and supervised usability evaluations until formally validated.

**Future production work required:** HTTPS, public domain, managed Postgres with migrations, account recovery/MFA, privacy consent, audit logs, durable offline event queue, robust device provisioning/revocation, app push notifications, supervised studies, enclosure and electrical testing, and formal device/human safety assessment.
