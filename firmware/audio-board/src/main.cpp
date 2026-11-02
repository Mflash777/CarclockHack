// =====================================================================
//  HackClock v2 - AUDIO board (classic ESP32 WROVER)
//   * Bluetooth speaker: phones connect to "HackClock" (A2DP sink + AVRCP track info/controls)
//   * Plays Home Assistant text-to-speech replies (MP3/WAV over HTTP)
//   * Alarm / timer / chime tones through the speaker
//   * Dims the TFT backlight (BLK pin)
//   * I2C SLAVE at 0x42 - the clock board (XIAO ESP32-S3) is the master
//
//  Wiring:  MAX98357A  BCLK->GPIO26  LRC->GPIO25  DIN->GPIO27  VIN->5V  GND->GND
//           I2C        SDA->GPIO21   SCL->GPIO22   (to the clock PCB "AUDIO" header)
//           TFT BLK    GPIO4
// =====================================================================
#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "AudioTools.h"
#include "BluetoothA2DPSink.h"
#if __has_include("AudioTools/AudioCodecs/CodecMP3Helix.h")
  #include "AudioTools/AudioCodecs/CodecMP3Helix.h"
#else
  #include "AudioCodecs/CodecMP3Helix.h"
#endif
#if __has_include("AudioTools/AudioCodecs/CodecWAV.h")
  #include "AudioTools/AudioCodecs/CodecWAV.h"
  #define HAVE_WAV 1
#elif __has_include("AudioCodecs/CodecWAV.h")
  #include "AudioCodecs/CodecWAV.h"
  #define HAVE_WAV 1
#endif

#define PIN_I2S_BCLK 26
#define PIN_I2S_LRC  25
#define PIN_I2S_DIN  27
#define PIN_SDA      21
#define PIN_SCL      22
#define PIN_BL       4
#define I2C_ADDR     0x42
#define LEDC_BL      0

// same command codes as the clock firmware (app.h)
enum : uint8_t {
  AC_WIFI_SSID = 0x01, AC_WIFI_PASS = 0x02, AC_WIFI_GO = 0x03,
  AC_URL_CLEAR = 0x10, AC_URL_APPEND = 0x11, AC_URL_PLAY = 0x12, AC_STOP_TTS = 0x13,
  AC_PLAY = 0x20, AC_PAUSE = 0x21, AC_NEXT = 0x22, AC_PREV = 0x23, AC_VOLUME = 0x24,
  AC_TONE_ALARM = 0x30, AC_TONE_STOP = 0x31, AC_CHIME = 0x32, AC_LISTEN_BEEP = 0x33,
  AC_BACKLIGHT = 0x40, AC_HOLD = 0x50,
};

// ------------------------------------------------------------------ audio output
I2SStream i2s;
BluetoothA2DPSink a2dp(i2s);
volatile float gain = 0.36f;          // from volume 0..10 (squared for a natural feel)
volatile uint8_t volume10 = 6;

void setVolume(uint8_t v) { volume10 = min<uint8_t>(v, 10); gain = (volume10 / 10.0f) * (volume10 / 10.0f); }

// Output stage with software volume; forwards format changes to the I2S driver.
class GainOut : public AudioStream {
 public:
  size_t write(const uint8_t* data, size_t len) {
    static int16_t tmp[512];
    size_t done = 0;
    float g = gain;
    while (done < len) {
      size_t n = min(len - done, sizeof(tmp));
      memcpy(tmp, data + done, n);
      for (size_t i = 0; i < n / 2; i++) tmp[i] = (int16_t)(tmp[i] * g);
      i2s.write((const uint8_t*)tmp, n);
      done += n;
    }
    return len;
  }
  void setAudioInfo(AudioInfo info) { AudioStream::setAudioInfo(info); i2s.setAudioInfo(info); }
  int available() { return 0; }
  size_t readBytes(uint8_t*, size_t) { return 0; }
};
GainOut out;

MP3DecoderHelix mp3;
EncodedAudioStream mp3Stream(&out, &mp3);
#ifdef HAVE_WAV
WAVDecoder wav;
EncodedAudioStream wavStream(&out, &wav);
#endif

void i2sDefault() { i2s.setAudioInfo(AudioInfo(44100, 2, 16)); }
void writeSilence(size_t bytes) {
  static const uint8_t zeros[256] = {0};
  while (bytes) { size_t n = min(bytes, sizeof(zeros)); i2s.write(zeros, n); bytes -= n; }
}

// ------------------------------------------------------------------ state
volatile bool btConnected = false, btPlaying = false, ttsActive = false, toneActive = false, holdOn = false;
bool pausedByUs = false;
char title[41] = "", artist[31] = "";
volatile uint8_t metaSeq = 0;
String ssid, pass, url, pendingUrl;
uint8_t status[74];

// ------------------------------------------------------------------ Bluetooth callbacks
void onA2dpData(const uint8_t* data, uint32_t len) {
  if (ttsActive || toneActive) return;           // a voice reply or alarm is using the speaker
  out.write(data, len);
}
void onConn(esp_a2d_connection_state_t s, void*) {
  btConnected = (s == ESP_A2D_CONNECTION_STATE_CONNECTED);
  if (!btConnected) { btPlaying = false; title[0] = artist[0] = 0; metaSeq++; }
}
void onAudioState(esp_a2d_audio_state_t s, void*) { btPlaying = (s == ESP_A2D_AUDIO_STATE_STARTED); }
void onMeta(uint8_t id, const uint8_t* text) {
  if (id == ESP_AVRC_MD_ATTR_TITLE)  { strncpy(title, (const char*)text, 40); title[40] = 0; }
  if (id == ESP_AVRC_MD_ATTR_ARTIST) { strncpy(artist, (const char*)text, 30); artist[30] = 0; }
  metaSeq++;
}
void onRate(uint16_t rate) { if (!ttsActive && !toneActive) i2s.setAudioInfo(AudioInfo(rate, 2, 16)); }

void pauseForUs() { if (btPlaying && !pausedByUs) { a2dp.pause(); pausedByUs = true; } }
void maybeResume() {
  if (pausedByUs && !holdOn && !ttsActive && !toneActive) { a2dp.play(); pausedByUs = false; }
}

// ------------------------------------------------------------------ I2C slave
struct Frame { uint8_t len; uint8_t d[127]; };
QueueHandle_t rxQueue;

void onI2cReceive(int n) {
  Frame f; f.len = 0;
  while (Wire.available() && f.len < sizeof(f.d)) f.d[f.len++] = Wire.read();
  while (Wire.available()) Wire.read();
  if (f.len) xQueueSend(rxQueue, &f, 0);
}
void onI2cRequest() { Wire.write(status, sizeof(status)); }

void buildStatus() {
  uint8_t s[74] = {0};
  s[0] = 0xA5;
  s[1] = (btConnected ? 0x01 : 0) | (btPlaying ? 0x02 : 0) | (ttsActive ? 0x04 : 0) |
         (toneActive ? 0x08 : 0) | (WiFi.status() == WL_CONNECTED ? 0x10 : 0);
  s[2] = volume10; s[3] = metaSeq;
  memcpy(s + 4, title, 40); memcpy(s + 44, artist, 30);
  memcpy(status, s, sizeof(s));
}

// ------------------------------------------------------------------ tones (synthesised sine)
struct Note { uint16_t f, ms; };
const Note alarmNotes[] = { {784,140},{0,40},{988,140},{0,40},{1175,140},{0,40},{1568,320},{0,600} };
const Note timerNotes[] = { {1319,120},{0,80},{1319,120},{0,80},{1319,120},{0,700} };
const Note chimeNotes[] = { {1047,110},{1319,110},{1568,220} };
const Note beepNotes[]  = { {1568,80} };

const Note* curTone = nullptr; int toneLen = 0, toneIdx = 0; bool toneLoop = false;
uint32_t toneNoteEnd = 0, toneStarted = 0; float phase = 0;

void startTone(const Note* t, int len, bool loop) {
  pauseForUs();
  curTone = t; toneLen = len; toneIdx = 0; toneLoop = loop; toneActive = true;
  toneNoteEnd = millis() + t[0].ms; toneStarted = millis(); phase = 0;
  i2sDefault();
}
void stopTone() { curTone = nullptr; toneActive = false; }

void serviceTone() {           // writes ~10 ms of audio per call
  if (!curTone) return;
  if (millis() >= toneNoteEnd) {
    if (++toneIdx >= toneLen) { if (!toneLoop) { stopTone(); return; } toneIdx = 0; }
    toneNoteEnd = millis() + curTone[toneIdx].ms;
  }
  static int16_t buf[441 * 2];
  float f = curTone[toneIdx].f;
  // alarms ramp from 30% to full over 30 s so you aren't blasted awake
  float ramp = toneLoop ? min(1.0f, 0.3f + (millis() - toneStarted) / 43000.0f) : 1.0f;
  float amp = f > 0 ? 12000.0f * ramp : 0;
  for (int i = 0; i < 441; i++) {
    int16_t v = (int16_t)(amp * sinf(phase));
    buf[2 * i] = buf[2 * i + 1] = v;
    phase += 2 * PI * f / 44100.0f;
    if (phase > 2 * PI) phase -= 2 * PI;
  }
  out.write((const uint8_t*)buf, sizeof(buf));
}

void playBlockingTone(const Note* t, int len) {
  startTone(t, len, false);
  while (curTone) serviceTone();
  writeSilence(1024);
  maybeResume();
}

// ------------------------------------------------------------------ TTS playback
void handleFrame(const Frame& f);

void playUrl(const String& u) {
  if (WiFi.status() != WL_CONNECTED) return;
  ttsActive = true; pauseForUs(); stopTone();
  HTTPClient http; WiFiClient client;
  http.setTimeout(8000);
  const char* keys[] = {"Content-Type"};
  bool ok = http.begin(client, u);
  if (ok) http.collectHeaders(keys, 1);
  if (ok && http.GET() == 200) {
    String ct = http.header("Content-Type");
    bool isWav = u.endsWith(".wav") || ct.indexOf("wav") >= 0;
#ifdef HAVE_WAV
    EncodedAudioStream& dec = isWav ? wavStream : mp3Stream;
#else
    EncodedAudioStream& dec = mp3Stream;
#endif
    dec.begin();
    WiFiClient* s = http.getStreamPtr();
    int remaining = http.getSize();             // -1 if unknown
    static uint8_t buf[1024];
    uint32_t lastData = millis();
    while (http.connected() && (remaining > 0 || remaining == -1) && ttsActive) {
      size_t a = s->available();
      if (a) {
        int c = s->readBytes(buf, min(a, sizeof(buf)));
        dec.write(buf, c);
        if (remaining > 0) remaining -= c;
        lastData = millis();
      } else {
        if (millis() - lastData > 3000) break;
        delay(2);
      }
      Frame f;                                   // allow STOP / volume during playback
      while (xQueueReceive(rxQueue, &f, 0) == pdTRUE) handleFrame(f);
      buildStatus();
    }
    dec.end();
  }
  http.end();
  writeSilence(2048);
  i2sDefault();
  ttsActive = false;
  maybeResume();
}

// ------------------------------------------------------------------ command handling
void handleFrame(const Frame& f) {
  uint8_t cmd = f.d[0];
  String payload; for (int i = 1; i < f.len; i++) payload += (char)f.d[i];
  uint8_t v = f.len > 1 ? f.d[1] : 0;
  switch (cmd) {
    case AC_WIFI_SSID: ssid = payload; break;
    case AC_WIFI_PASS: pass = payload; break;
    case AC_WIFI_GO:   if (WiFi.status() != WL_CONNECTED && ssid.length()) WiFi.begin(ssid.c_str(), pass.c_str()); break;
    case AC_URL_CLEAR: url = ""; break;
    case AC_URL_APPEND: url += payload; break;
    case AC_URL_PLAY:  pendingUrl = url; ttsActive = true; break;   // flag now so status shows "busy"
    case AC_STOP_TTS:  ttsActive = false; break;
    case AC_PLAY:  pausedByUs = false; a2dp.play(); break;
    case AC_PAUSE: pausedByUs = false; a2dp.pause(); break;
    case AC_NEXT:  a2dp.next(); break;
    case AC_PREV:  a2dp.previous(); break;
    case AC_VOLUME: setVolume(v); break;
    case AC_TONE_ALARM: if (v == 1) startTone(timerNotes, 6, true); else startTone(alarmNotes, 8, true); break;
    case AC_TONE_STOP:  stopTone(); maybeResume(); break;
    case AC_CHIME:       if (!ttsActive && !toneActive) playBlockingTone(chimeNotes, 3); break;
    case AC_LISTEN_BEEP: if (!ttsActive && !toneActive) playBlockingTone(beepNotes, 1); break;
    case AC_BACKLIGHT:  ledcWrite(LEDC_BL, v); break;
    case AC_HOLD:       holdOn = v; if (holdOn) pauseForUs(); else maybeResume(); break;
  }
}

// ------------------------------------------------------------------ setup / loop
void setup() {
  Serial.begin(115200);
  ledcSetup(LEDC_BL, 5000, 8); ledcAttachPin(PIN_BL, LEDC_BL); ledcWrite(LEDC_BL, 255);
  setVolume(6);
  rxQueue = xQueueCreate(16, sizeof(Frame));

  auto cfg = i2s.defaultConfig(TX_MODE);
  cfg.pin_bck = PIN_I2S_BCLK; cfg.pin_ws = PIN_I2S_LRC; cfg.pin_data = PIN_I2S_DIN;
  cfg.sample_rate = 44100; cfg.channels = 2; cfg.bits_per_sample = 16;
  i2s.begin(cfg);

  a2dp.set_stream_reader(onA2dpData, false);     // we write to I2S ourselves (volume + muting)
  a2dp.set_on_connection_state_changed(onConn, nullptr);
  a2dp.set_on_audio_state_changed(onAudioState, nullptr);
  a2dp.set_avrc_metadata_attribute_mask(ESP_AVRC_MD_ATTR_TITLE | ESP_AVRC_MD_ATTR_ARTIST);
  a2dp.set_avrc_metadata_callback(onMeta);
  a2dp.set_sample_rate_callback(onRate);
  a2dp.set_auto_reconnect(true);
  a2dp.start("HackClock");

  WiFi.mode(WIFI_STA);                           // credentials arrive from the clock board over I2C
  WiFi.setSleep(true);                           // required when WiFi and Bluetooth share the radio

  buildStatus();
  Wire.onReceive(onI2cReceive);
  Wire.onRequest(onI2cRequest);
  Wire.begin((uint8_t)I2C_ADDR, PIN_SDA, PIN_SCL, 100000);
  Serial.println("HackClock audio board ready");
}

void loop() {
  Frame f;
  while (xQueueReceive(rxQueue, &f, 0) == pdTRUE) handleFrame(f);
  if (pendingUrl.length()) { String u = pendingUrl; pendingUrl = ""; playUrl(u); }
  if (toneActive) serviceTone(); else delay(5);
  maybeResume();
  buildStatus();
}
