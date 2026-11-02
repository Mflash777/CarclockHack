// I2C link to the audio board (classic ESP32 WROVER at address 0x42).
// The audio board does Bluetooth music, plays Home Assistant's spoken replies,
// alarm/chime tones through the speaker, and dims the TFT backlight.
#include "app.h"
#include <Wire.h>
#include <WiFi.h>
#include "pins.h"

AudioStatus audio;
volatile bool audioTtsBusy = false;

static SemaphoreHandle_t urlLock;
static String pendingUrl;
static uint32_t lastGood = 0, lastWifiPush = 0;

static bool sendFrame(uint8_t cmd, const uint8_t* data, size_t n) {
  Wire.beginTransmission(I2C_ADDR_AUDIO);
  Wire.write(cmd);
  if (n) Wire.write(data, n);
  return Wire.endTransmission() == 0;
}

static bool sendString(uint8_t cmd, const String& s) {
  return sendFrame(cmd, (const uint8_t*)s.c_str(), min((size_t)s.length(), (size_t)110));
}

void audioCmd(uint8_t cmd, int value) {
  uint8_t v = (uint8_t)constrain(value, 0, 255);
  sendFrame(cmd, &v, value >= 0 ? 1 : 0);
}

void audioQueueUrl(const String& url) {
  xSemaphoreTake(urlLock, portMAX_DELAY); pendingUrl = url; xSemaphoreGive(urlLock);
  audioTtsBusy = true;                         // assume busy until the board says otherwise
}

void audioBegin() {
  urlLock = xSemaphoreCreateMutex();
}

static void pushWifi() {
  if (WiFi.status() != WL_CONNECTED) return;
  sendString(AC_WIFI_SSID, WiFi.SSID());
  sendString(AC_WIFI_PASS, WiFi.psk());
  sendFrame(AC_WIFI_GO, nullptr, 0);
}

// Status frame from the audio board (74 bytes):
// [0]=0xA5 magic [1]=flags [2]=volume(0..10) [3]=seq [4..43]=title [44..73]=artist
void audioPoll() {
  static uint32_t lastPoll = 0;
  if (millis() - lastPoll < 400) return;
  lastPoll = millis();

  // forward a queued TTS URL in <=100 byte chunks
  String url;
  xSemaphoreTake(urlLock, portMAX_DELAY); url = pendingUrl; pendingUrl = ""; xSemaphoreGive(urlLock);
  if (url.length()) {
    sendFrame(AC_URL_CLEAR, nullptr, 0);
    for (unsigned i = 0; i < url.length(); i += 100) sendString(AC_URL_APPEND, url.substring(i, i + 100));
    sendFrame(AC_URL_PLAY, nullptr, 0);
  }

  uint8_t buf[74];
  int n = Wire.requestFrom((int)I2C_ADDR_AUDIO, 74);
  if (n == 74) {
    for (int i = 0; i < 74; i++) buf[i] = Wire.read();
    if (buf[0] == 0xA5) {
      lastGood = millis();
      bool wasLinked = audio.linked;
      audio.linked      = true;
      audio.btConnected = buf[1] & 0x01;
      audio.playing     = buf[1] & 0x02;
      audio.ttsPlaying  = buf[1] & 0x04;
      audio.toneActive  = buf[1] & 0x08;
      audio.wifi        = buf[1] & 0x10;
      audio.volume      = buf[2];
      if (buf[3] != audio.seq) {
        audio.seq = buf[3];
        char t[41], a[31];
        memcpy(t, buf + 4, 40); t[40] = 0;
        memcpy(a, buf + 44, 30); a[30] = 0;
        audio.title = t; audio.artist = a;
        dataDirty = true;
      }
      if (!url.length()) audioTtsBusy = audio.ttsPlaying;
      if (!wasLinked) audioCmd(AC_VOLUME, cfg.volume);
      if (!audio.wifi && millis() - lastWifiPush > 15000) { lastWifiPush = millis(); pushWifi(); }
    }
  } else {
    while (Wire.available()) Wire.read();
  }
  if (millis() - lastGood > 3000) { audio.linked = false; audioTtsBusy = false; }
}
