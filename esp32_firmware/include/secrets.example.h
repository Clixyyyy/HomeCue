#pragma once
// 1) Rename this file to secrets.h (the real file is excluded from Git).
// 2) Use the SAME local Wi-Fi network as the backend PC.
#define WIFI_SSID "Your_WiFi_Name"
#define WIFI_PASSWORD "Your_WiFi_Password"
// Example: IP from Windows ipconfig. Do NOT write 127.0.0.1 here.
#define HOMECUE_SERVER_URL "http://192.168.1.12:8000"
// Website -> My Home -> Home setup -> generate one-time device token.
#define HOMECUE_HOME_ID 1
#define HOMECUE_DEVICE_TOKEN "PASTE_ONE_TIME_DEVICE_TOKEN_HERE"
// Optional RFID-tag mapping (copy hexadecimal UID printed by Serial Monitor).
// Without these, tags are logged but no multi-step task audio is attempted.
#define FIRST_TASK_TAG_UID ""
#define SECOND_TASK_TAG_UID ""
// Set true only AFTER checking module voltage, pinout, speaker and microSD compatibility.
#define ENABLE_PIR_SENSOR false
#define ENABLE_RTC_MODULE false
#define ENABLE_AUDIO_MODULE false
