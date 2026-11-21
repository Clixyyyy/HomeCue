// HomeCue IoT bench station for the exact parts visible in the user's photos:
// ESP32-WROOM, MFRC522 (13.56MHz) reader, possible HW-416 PIR, DS3231 RTC,
// DFPlayer Mini-style audio + Visaton 8-ohm 2W speaker.
// All physical outputs are local and non-safety-critical. No doors or appliances controlled.
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <RTClib.h>
#include <ArduinoJson.h>
#include <DFRobotDFPlayerMini.h>
#include "secrets.h"

// Explicit GPIO assignments: check the labels on YOUR particular ESP32 board.
// RC522 SPI: SS=25, SCK=18, MISO=19, MOSI=23, RST=27.
// PIR OUT=32 (input must be 3.3V safe); DS3231 SDA=21/SCL=22.
// MP3 module UART: ESP32 RX=16 <--- DFPlayer TX; ESP32 TX=17 ---> DFPlayer RX through 1k resistor.
// Optional indicator LED GPIO26 -> 220-330ohm resistor -> LED -> GND.
constexpr int RC522_SS = 25;
constexpr int RC522_RST = 27;
constexpr int PIN_PIR = 32;
constexpr int PIN_INDICATOR = 26;
constexpr int PIN_MP3_RX = 16;
constexpr int PIN_MP3_TX = 17;
constexpr int PIN_RTC_SDA = 21;
constexpr int PIN_RTC_SCL = 22;

constexpr unsigned long HEARTBEAT_INTERVAL_MS = 60000UL;
constexpr unsigned long WIFI_RETRY_MS = 10000UL;
constexpr unsigned long RFID_COOLDOWN_MS = 2500UL;
constexpr unsigned long PIR_SETTLE_MS = 30000UL;
constexpr unsigned long PIR_COOLDOWN_MS = 12000UL;

MFRC522 reader(RC522_SS, RC522_RST);
RTC_DS3231 rtc;
HardwareSerial mp3Uart(2);
DFRobotDFPlayerMini player;
bool rtcReady = false;
bool audioReady = false;
bool pirPrevious = false;
bool pirWarmedUp = false;
unsigned long bootedAt = 0;
unsigned long lastWifiTry = 0;
unsigned long lastHeartbeat = 0;
unsigned long lastPirEvent = 0;
unsigned long lastTag = 0;
String previousUid = "";
String firstTag = String(FIRST_TASK_TAG_UID);
String secondTag = String(SECOND_TASK_TAG_UID);
uint8_t taskStep = 0;

String uidHex() {
  String uid;
  for (byte i = 0; i < reader.uid.size; i++) {
    if (reader.uid.uidByte[i] < 0x10) uid += '0';
    uid += String(reader.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  return uid;
}

bool sendPost(const String& path, JsonDocument &json) {
  if (WiFi.status() != WL_CONNECTED) return false;
  WiFiClient client;
  HTTPClient http;
  const String url = String(HOMECUE_SERVER_URL) + path;
  if (!http.begin(client, url)) return false;
  http.setTimeout(3000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", String(HOMECUE_DEVICE_TOKEN));
  String payload;
  serializeJson(json, payload);
  const int response = http.POST(payload);
  const bool ok = response >= 200 && response < 300;
  Serial.printf("[API] POST %s -> %d %s\n", path.c_str(), response, ok ? "OK" : "FAILED");
  // Sensitive device credentials are never printed.
  http.end();
  return ok;
}

void sendEvent(const char* module, const char* kind, const String& message) {
  JsonDocument body;
  body["module"] = module;
  body["kind"] = kind;
  body["message"] = message;
  const bool sent = sendPost("/api/device/" + String(HOMECUE_HOME_ID) + "/events", body);
  if (!sent) Serial.println("[API] Event not delivered (offline events are NOT queued in this version)");
}

void heartbeat() {
  JsonDocument body;
  sendPost("/api/device/" + String(HOMECUE_HOME_ID) + "/heartbeat", body);
}

void playPrompt(uint8_t number) {
  if (!audioReady) return;
  player.volume(8);            // Deliberately low to protect the 8-ohm 2 W speaker.
  player.playMp3Folder(number); // /mp3/0001.mp3, /mp3/0002.mp3 on compatible SD.
}

void handleTag() {
  if (!reader.PICC_IsNewCardPresent() || !reader.PICC_ReadCardSerial()) return;
  const String uid = uidHex();
  reader.PICC_HaltA();
  reader.PCD_StopCrypto1();
  const unsigned long time = millis();
  if (uid == previousUid && time - lastTag < RFID_COOLDOWN_MS) return;
  previousUid = uid;
  lastTag = time;
  Serial.printf("[RFID] Tag UID: %s\n", uid.c_str());
  digitalWrite(PIN_INDICATOR, HIGH);
  delay(130); // short indicator pulse, not used for safety timing
  digitalWrite(PIN_INDICATOR, LOW);
  sendEvent("task", "tag_scan", "Compatible tag scanned at task station (UID kept locally on ESP32 Serial Monitor)");

  // Demo of a simple two-step sequential activity. No task-completion claim from scanning alone.
  if (firstTag.length() > 0 && uid == firstTag) {
    taskStep = 1;
    playPrompt(1);
    sendEvent("task", "cue_played", "Step 1 tag registered; local prompt requested");
  } else if (secondTag.length() > 0 && uid == secondTag && taskStep == 1) {
    taskStep = 2;
    playPrompt(2);
    sendEvent("task", "cue_played", "Step 2 tag registered; local prompt requested");
  }
}

void handlePIR() {
  if (!ENABLE_PIR_SENSOR) return;
  const unsigned long time = millis();
  // PIRs need warm-up; avoid false initial event.
  if (time - bootedAt < PIR_SETTLE_MS) return;
  if (!pirWarmedUp) {pirPrevious = digitalRead(PIN_PIR) == HIGH;pirWarmedUp=true;}
  const bool current = digitalRead(PIN_PIR) == HIGH;
  if (current != pirPrevious && time - lastPirEvent >= PIR_COOLDOWN_MS) {
    pirPrevious = current;
    lastPirEvent = time;
    sendEvent("night", current ? "motion_detected" : "motion_cleared", current ? "Motion detected in test area" : "No motion currently detected in test area");
  }
}

void handleRTC() {
  if (!ENABLE_RTC_MODULE || !rtcReady) return;
  static unsigned long lastClock = 0;
  if (millis() - lastClock > 60000UL) {
    lastClock = millis();
    const DateTime t = rtc.now();
    Serial.printf("[RTC] %04d-%02d-%02d %02d:%02d:%02d (board local time)\n", t.year(),t.month(),t.day(),t.hour(),t.minute(),t.second());
  }
}

void setup() {
  Serial.begin(115200);
  bootedAt = millis();
  pinMode(PIN_INDICATOR, OUTPUT);
  digitalWrite(PIN_INDICATOR, LOW);
  SPI.begin(18,19,23,RC522_SS);
  reader.PCD_Init();
  Serial.println("\nHomeCue ESP32 lab station starting");
  Serial.println("Place a compatible 13.56 MHz RFID tag close to the RC522 antenna");
  pinMode(PIN_PIR, INPUT);

  if (ENABLE_RTC_MODULE) {
    Wire.begin(PIN_RTC_SDA, PIN_RTC_SCL);
    rtcReady = rtc.begin();
    Serial.println(rtcReady ? "DS3231 detected" : "RTC missing - continuing without it");
    if (rtcReady && rtc.lostPower()) Serial.println("RTC lost power; set its clock intentionally before using schedules");
  }
  if (ENABLE_AUDIO_MODULE) {
    mp3Uart.begin(9600, SERIAL_8N1, PIN_MP3_RX, PIN_MP3_TX);
    audioReady = player.begin(mp3Uart);
    Serial.println(audioReady ? "MP3 module detected" : "MP3 module not found / wrong SD - audio disabled");
    if (audioReady) player.volume(8);
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Wi-Fi connecting");
  for (int i=0;i<15 && WiFi.status()!=WL_CONNECTED;i++) {delay(500);Serial.print(".");}
  Serial.println();
  if (WiFi.status()==WL_CONNECTED) {Serial.print("ESP32 local IP: ");Serial.println(WiFi.localIP());}
  else Serial.println("Not online. RFID still works in serial monitor, but events are not queued.");
}

void loop() {
  handleTag();
  handlePIR();
  handleRTC();
  const unsigned long t = millis();
  if (WiFi.status()!=WL_CONNECTED && t-lastWifiTry>=WIFI_RETRY_MS) {
    lastWifiTry=t;
    WiFi.reconnect();
  }
  if (WiFi.status()==WL_CONNECTED && (lastHeartbeat==0 || t-lastHeartbeat>=HEARTBEAT_INTERVAL_MS)) {
    lastHeartbeat=t;
    heartbeat();
  }
  delay(15);
}
