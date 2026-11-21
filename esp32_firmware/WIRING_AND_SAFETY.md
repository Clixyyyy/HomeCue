# ESP32 lab-station wiring — use only verified low-voltage connections

**STOP before connecting power:** verify your exact ESP32 and sensor pin labels. The photographed metal SMPS is a mains-powered exposed-terminal supply; do NOT use it on a desk or wire to household AC during these tests. Use a **known-safe USB data cable and USB power** for the ESP32. No stove/door/medicine automation.

## Start with one module at a time

1. Start with **ESP32 over USB only**, install PlatformIO in VS Code, open Serial Monitor and upload firmware.
2. Power off. Connect RC522 using table below, then check Serial Monitor for tag UID. **RC522 requires 3.3 V**. A 125 kHz tag will not work with a 13.56 MHz RC522.
3. Confirm from the board marking whether the photo's purported HW-416B is **actually a PIR board** and determine its power range and logic output. Connect PIR only when output is **3.3 V safe**. If HIGH is 5 V, use a voltage divider or level shifter.
4. DS3231 is optional; be careful of coin-cell charging boards. Some low-cost DS3231 breakout boards include a charging path intended for rechargeable cells: do not fit a non-rechargeable CR2032 without checking the exact circuit.
5. DFPlayer Mini-style audio optional: the photo's **64GB microSDXC** may not be supported. Manufacturer supports up to 32GB FAT16/FAT32; use a separate compatible FAT32 ≤32GB microSD for audio. Verify DFPlayer pin labels and speaker leads before connecting. The 8-ohm 2W speaker needs low audio volume.

## Pin table (example for common 30/38-pin ESP32 DevKit)

| Module | Component pin | ESP32 pin | Additional note |
|---|---|---|---|
| RC522 | 3.3V | 3V3 | **Never 5V** |
| RC522 | GND | GND | Common ground |
| RC522 | SDA / SS | GPIO25 | SPI chip-select, NOT I2C SDA |
| RC522 | SCK | GPIO18 | SPI clock |
| RC522 | MOSI | GPIO23 | SPI TX |
| RC522 | MISO | GPIO19 | SPI RX |
| RC522 | RST | GPIO27 | Reset |
| RC522 | IRQ | Not connected | Unused |
| PIR (if verified) | OUT | GPIO32 | Only when output ≤3.3 V |
| PIR | VCC | Per module marking | Verify board requirements; do not assume 3.3 or 5 V |
| PIR | GND | GND | Common ground |
| DS3231 (optional) | VCC | 3V3 | Verify module and backup battery design |
| DS3231 | SDA | GPIO21 | I2C data |
| DS3231 | SCL | GPIO22 | I2C clock |
| DS3231 | GND | GND | Common ground |
| DFPlayer (optional) | RX | GPIO17 through 1kΩ | ESP32 TX2; check DFPlayer power/input spec |
| DFPlayer (optional) | TX | GPIO16 | ESP32 RX2; verify logic level |
| DFPlayer (optional) | VCC | Regulated 5V or compliant source | Separate current budget, common GND |
| DFPlayer (optional) | SPK1/SPK2 | Speaker wires | 8Ω 2W; keep volume low |
| LED (optional) | Anode (+) | GPIO26 via 220–330Ω | Don't drive LED directly without resistor |
| LED (optional) | Cathode (−) | GND | Indicator only |

You may have pin conflicts with other ESP32 board variants; check the pinout first. Flash mode pins (GPIO0, GPIO2, GPIO5, GPIO12, GPIO15) are avoided in this table. These connectors appear in a few of your photos, but do not rely on wire colours alone for polarity.

## Audio file arrangement

On a **compatible FAT32 ≤32GB microSD**:

`/mp3/0001.mp3` — short cue after Step 1 tag

`/mp3/0002.mp3` — short cue after Step 2 tag

In `include/secrets.h`, set `ENABLE_AUDIO_MODULE true` only after wiring and verifying audio hardware. Change `FIRST_TASK_TAG_UID` and `SECOND_TASK_TAG_UID` to the distinct IDs printed in Serial Monitor. Tags close to the RC522 are detected; attaching a tag to an object does NOT monitor it across a room.

## Build in VS Code

- Install the **PlatformIO IDE** extension.
- Open `esp32_firmware` as a project.
- Copy `include/secrets.example.h` to `include/secrets.h`, edit Wi-Fi credentials and backend URL + home ID + device token.
- Start backend on PC bound to `0.0.0.0` on an isolated/trusted private LAN only. Use your PC's IPv4 address from `ipconfig`, not `127.0.0.1` inside the ESP32.
- With RC522 attached, click PlatformIO **Build**, then **Upload**; open **Monitor (115200 baud)**.
- Website and mobile app Activity show the same `tag_scan` events. If the board is offline, events are **not queued**; use Serial Monitor to debug.

**Safety & research note:** RFID scanning only demonstrates a user-interaction step. It does not prove a real-world activity is complete. PIR detects movement, not identity or whether someone is safe. Do not use this test setup unsupervised with a person living with dementia.
