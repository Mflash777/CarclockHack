// =====================================================================
//  HackClock v2 - WiFi alarm clock + Bluetooth speaker + voice assistant
//  Hack Club Half Life (display week)
//  This is the CLOCK board (Seeed XIAO ESP32-S3):
//    7-segment time (HT16K33, I2C), 2.0" TFT (ST7789) info pages, buttons, buzzers,
//    INMP441 mic -> Home Assistant voice, I2C link to the AUDIO board (Bluetooth + speaker).
// =====================================================================
#include "app.h"
#include "pins.h"
#include "web_page.h"
#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <Wire.h>
#include "esp_sntp.h"
#include <TFT_eSPI.h>
#include <Adafruit_LEDBackpack.h>
#include <RTClib.h>
#include <WiFiManager.h>

extern volatile int  voiceHoldRequest;
extern volatile bool voiceBeepRequest;

Settings cfg;
Preferences prefs;

// ------------------------------------------------------------------ settings storage
void loadSettings() {
  prefs.begin("clock", true);
  cfg.tz         = prefs.getString("tz", cfg.tz);
  cfg.h24        = prefs.getBool("h24", cfg.h24);
  for (int i = 0; i < 2; i++) {
    String k = "a" + String(i);
    cfg.alarm[i].hour    = prefs.getUChar((k + "h").c_str(), i == 0 ? 7 : 8);
    cfg.alarm[i].minute  = prefs.getUChar((k + "m").c_str(), 0);
    cfg.alarm[i].on      = prefs.getBool((k + "on").c_str(), false);
    cfg.alarm[i].days    = prefs.getUChar((k + "d").c_str(), i == 0 ? 0x3E : 0x41);
    cfg.alarm[i].oneShot = prefs.getBool((k + "o").c_str(), false);
  }
  cfg.symbols    = prefs.getString("sym", cfg.symbols);
  cfg.finnhub    = prefs.getString("fh", cfg.finnhub);
  cfg.ntfyTopic  = prefs.getString("ntfy", "");
  cfg.rssUrl     = prefs.getString("rss", cfg.rssUrl);
  cfg.lat        = prefs.getFloat("lat", cfg.lat);
  cfg.lon        = prefs.getFloat("lon", cfg.lon);
  cfg.fahrenheit = prefs.getBool("degF", cfg.fahrenheit);
  cfg.nightStart = prefs.getUChar("nS", cfg.nightStart);
  cfg.nightEnd   = prefs.getUChar("nE", cfg.nightEnd);
  cfg.brightness = prefs.getUChar("bri", cfg.brightness);
  cfg.pageSeconds= prefs.getUChar("pgs", cfg.pageSeconds);
  cfg.haHost     = prefs.getString("haH", cfg.haHost);
  cfg.haPort     = prefs.getUShort("haP", cfg.haPort);
  cfg.haToken    = prefs.getString("haT", cfg.haToken);
  cfg.wakeWord   = prefs.getBool("wake", cfg.wakeWord);
  cfg.volume     = prefs.getUChar("vol", cfg.volume);
  cfg.alarmSpeaker = prefs.getBool("aSpk", cfg.alarmSpeaker);
  prefs.end();
  if (cfg.ntfyTopic.isEmpty()) {
    char buf[32]; snprintf(buf, sizeof(buf), "hackclock-%08lx", (unsigned long)esp_random());
    cfg.ntfyTopic = buf;
  }
}

void saveSettings() {
  prefs.begin("clock", false);
  prefs.putString("tz", cfg.tz);
  prefs.putBool("h24", cfg.h24);
  for (int i = 0; i < 2; i++) {
    String k = "a" + String(i);
    prefs.putUChar((k + "h").c_str(), cfg.alarm[i].hour);
    prefs.putUChar((k + "m").c_str(), cfg.alarm[i].minute);
    prefs.putBool((k + "on").c_str(), cfg.alarm[i].on);
    prefs.putUChar((k + "d").c_str(), cfg.alarm[i].days);
    prefs.putBool((k + "o").c_str(), cfg.alarm[i].oneShot);
  }
  prefs.putString("sym", cfg.symbols);
  prefs.putString("fh", cfg.finnhub);
  prefs.putString("ntfy", cfg.ntfyTopic);
  prefs.putString("rss", cfg.rssUrl);
  prefs.putFloat("lat", cfg.lat);
  prefs.putFloat("lon", cfg.lon);
  prefs.putBool("degF", cfg.fahrenheit);
  prefs.putUChar("nS", cfg.nightStart);
  prefs.putUChar("nE", cfg.nightEnd);
  prefs.putUChar("bri", cfg.brightness);
  prefs.putUChar("pgs", cfg.pageSeconds);
  prefs.putString("haH", cfg.haHost);
  prefs.putUShort("haP", cfg.haPort);
  prefs.putString("haT", cfg.haToken);
  prefs.putBool("wake", cfg.wakeWord);
  prefs.putUChar("vol", cfg.volume);
  prefs.putBool("aSpk", cfg.alarmSpeaker);
  prefs.end();
}

// ------------------------------------------------------------------ hardware
TFT_eSPI tft;
Adafruit_7segment seg;
RTC_DS3231 rtc;
bool rtcOk = false, segOk = false;
WebServer server(80);
WiFiManager wm;
bool portalRunning = false, serverStarted = false;
volatile bool ntpSynced = false;
#define LEDC_BUZZ 0

// ------------------------------------------------------------------ helpers
bool timeValid() { return time(nullptr) > 1700000000; }

bool isNight(const tm& t) {
  if (cfg.nightStart == cfg.nightEnd) return false;
  if (cfg.nightStart < cfg.nightEnd) return t.tm_hour >= cfg.nightStart && t.tm_hour < cfg.nightEnd;
  return t.tm_hour >= cfg.nightStart || t.tm_hour < cfg.nightEnd;
}

String fmtTime(int h, int m) {
  char b[12];
  if (cfg.h24) snprintf(b, sizeof(b), "%02d:%02d", h, m);
  else snprintf(b, sizeof(b), "%d:%02d %s", (h % 12) ? h % 12 : 12, m, h < 12 ? "AM" : "PM");
  return b;
}

String fmtTimeSpoken(int h, int m) {
  char b[16];
  int hh = (h % 12) ? h % 12 : 12;
  if (m == 0) snprintf(b, sizeof(b), "%d %s", hh, h < 12 ? "AM" : "PM");
  else snprintf(b, sizeof(b), "%d:%02d %s", hh, m, h < 12 ? "AM" : "PM");
  return b;
}

String daysText(uint8_t d) {
  if (d == 0x7F) return "Every day";
  if (d == 0x3E) return "Weekdays";
  if (d == 0x41) return "Weekends";
  const char* n = "SMTWTFS"; String s;
  for (int i = 0; i < 7; i++) s += (d & (1 << i)) ? n[i] : '-';
  return s;
}

void onNtpSync(struct timeval*) { ntpSynced = true; }

// ------------------------------------------------------------------ buzzer (backup sound)
struct Note { uint16_t f, ms; };
const Note alarmTune[] = {
  {1047,120},{0,60},{1319,120},{0,60},{1568,120},{0,60},{2093,240},{0,500},
  {1568,120},{0,60},{2093,120},{0,60},{1568,120},{0,60},{2093,240},{0,700}
};
const Note chimeTune[] = { {1568,90},{0,40},{2093,90},{0,40},{2637,160} };
const Note beepTune[]  = { {1760,70} };
const Note* tune = nullptr; int tuneLen = 0, tuneIdx = 0; bool tuneLoop = false;
uint32_t noteEnds = 0;

void playTune(const Note* t, int len, bool loop) { tune = t; tuneLen = len; tuneIdx = -1; tuneLoop = loop; noteEnds = 0; }
void stopTune() { tune = nullptr; ledcWriteTone(LEDC_BUZZ, 0); }
void serviceBuzzer() {
  if (!tune || millis() < noteEnds) return;
  if (++tuneIdx >= tuneLen) { if (!tuneLoop) { stopTune(); return; } tuneIdx = 0; }
  ledcWriteTone(LEDC_BUZZ, tune[tuneIdx].f);
  noteEnds = millis() + tune[tuneIdx].ms;
}

// short sounds: speaker if the audio board is there, buzzer otherwise
void chime() { if (audio.linked) audioCmd(AC_CHIME); else playTune(chimeTune, 5, false); }

// ------------------------------------------------------------------ alarms + timer
volatile bool ringing = false;
volatile time_t timerEnd = 0;
bool ringIsTimer = false, ringOnSpeaker = false;
time_t ringStarted = 0, snoozeUntil = 0;
int lastAlarmMinute = -1;

void startRinging(bool timer) {
  ringing = true; ringIsTimer = timer; ringStarted = time(nullptr); snoozeUntil = 0;
  ringOnSpeaker = audio.linked && cfg.alarmSpeaker;
  if (ringOnSpeaker) audioCmd(AC_TONE_ALARM, timer ? 1 : 0);
  else playTune(alarmTune, 16, true);
  dataDirty = true;
}
void stopRingSound() { stopTune(); if (ringOnSpeaker || audio.linked) audioCmd(AC_TONE_STOP); }
void snooze()  { if (ringIsTimer) { ringing = false; stopRingSound(); return; }
                 ringing = false; stopRingSound(); snoozeUntil = time(nullptr) + 9 * 60; dataDirty = true; }
void dismiss() { ringing = false; stopRingSound(); snoozeUntil = 0; dataDirty = true; }

void checkAlarms(const tm& t) {
  int stamp = t.tm_yday * 1440 + t.tm_hour * 60 + t.tm_min;
  if (stamp != lastAlarmMinute) {
    lastAlarmMinute = stamp;
    for (auto& a : cfg.alarm)
      if (a.on && a.hour == t.tm_hour && a.minute == t.tm_min && (a.days & (1 << t.tm_wday)) && !ringing) {
        startRinging(false);
        if (a.oneShot) { a.on = false; a.oneShot = false; saveSettings(); }
      }
  }
  time_t now = time(nullptr);
  if (snoozeUntil && now >= snoozeUntil) startRinging(false);
  if (timerEnd && now >= timerEnd) { timerEnd = 0; startRinging(true); }
  if (ringing && now - ringStarted > (ringIsTimer ? 120 : 600)) dismiss();
}

// ------------------------------------------------------------------ buttons
enum Btn { B_NONE, B_SNOOZE, B_MODE, B_UP, B_DOWN, B_TALK };
enum Evt { E_NONE, E_SHORT, E_LONG, E_REPEAT, E_VLONG };   // E_VLONG = held 8 s

Btn readLadder() {
  int mv = analogReadMilliVolts(PIN_BUTTONS);
  if (mv < LADDER_SNOOZE_MAX) return B_SNOOZE;
  if (mv < LADDER_MODE_MAX)   return B_MODE;
  if (mv < LADDER_UP_MAX)     return B_UP;
  if (mv < LADDER_DOWN_MAX)   return B_DOWN;
  if (mv < LADDER_TALK_MAX)   return B_TALK;
  return B_NONE;
}

Btn stableBtn = B_NONE, rawLast = B_NONE;
uint32_t rawSince = 0, pressedAt = 0, lastRepeat = 0;
bool longFired = false, vlongFired = false;

Evt pollButtons(Btn& which) {
  which = B_NONE;
  Btn r = readLadder();
  uint32_t now = millis();
  if (r != rawLast) { rawLast = r; rawSince = now; }
  if (now - rawSince < 30) return E_NONE;
  if (r != stableBtn) {
    Btn prev = stableBtn; stableBtn = r;
    if (r != B_NONE) { pressedAt = now; longFired = false; vlongFired = false; lastRepeat = now; return E_NONE; }
    if (prev != B_NONE && !longFired) { which = prev; return E_SHORT; }
    return E_NONE;
  }
  if (stableBtn != B_NONE) {
    uint32_t held = now - pressedAt;
    if (!longFired && held > 1500) { longFired = true; which = stableBtn; return E_LONG; }
    if (longFired && !vlongFired && held > 8000) { vlongFired = true; which = stableBtn; return E_VLONG; }
    if ((stableBtn == B_UP || stableBtn == B_DOWN) && held > 600 && now - lastRepeat > 140) {
      lastRepeat = now; which = stableBtn; return E_REPEAT;
    }
  }
  return E_NONE;
}

// ------------------------------------------------------------------ UI
enum Page { P_HOME, P_MUSIC, P_STOCKS, P_NEWS, P_MSG, P_COUNT };
Page page = P_HOME;
uint32_t pageSince = 0, manualUntil = 0, replyShownAt = 0;
int  newsIdx = 0; uint32_t newsSince = 0;
bool editing = false; int editAlarm = 0, editField = 0;
bool forceNight = false, needRedraw = true, voicePanel = false;

const uint16_t C_BG = TFT_BLACK, C_ACC = 0xFD20, C_DIM = 0x8410, C_UP = 0x07E8, C_DN = 0xF9A6, C_BAR = 0x18E3, C_VOICE = 0x3A7F;

int drawWrapped(const String& text, int x, int y, int w, int font, int lineH, int maxLines, uint16_t col, uint16_t bg = C_BG) {
  tft.setTextColor(col, bg);
  String line, word; int lines = 0;
  String t = text + " ";
  for (unsigned i = 0; i < t.length() && lines < maxLines; i++) {
    char c = t[i];
    if (c == ' ' || c == '\n') {
      String trial = line.isEmpty() ? word : line + " " + word;
      if (tft.textWidth(trial, font) > w && !line.isEmpty()) { tft.drawString(line, x, y + lines * lineH, font); lines++; line = word; }
      else line = trial;
      word = "";
      if (c == '\n' && lines < maxLines) { tft.drawString(line, x, y + lines * lineH, font); lines++; line = ""; }
    } else word += c;
  }
  if (!line.isEmpty() && lines < maxLines) { tft.drawString(line, x, y + lines * lineH, font); lines++; }
  return lines;
}

void drawHeader(const char* title) {
  tft.fillRect(0, 0, 320, 30, C_BAR);
  tft.setTextColor(C_ACC, C_BAR); tft.setTextDatum(ML_DATUM);
  tft.drawString(title, 10, 15, 4);
  tft.setTextDatum(MR_DATUM); tft.setTextColor(TFT_WHITE, C_BAR);
  String right;
  if (ringing) right = ringIsTimer ? "TIMER!" : "ALARM!";
  else if (timerEnd) { long l = timerEnd - time(nullptr); char b[16]; snprintf(b, sizeof(b), "T %ld:%02ld", l / 60, l % 60); right = b; }
  else if (snoozeUntil) right = "Snoozing";
  else for (auto& a : cfg.alarm) if (a.on) { right = "AL " + fmtTime(a.hour, a.minute); break; }
  tft.drawString(right, 246, 15, 2);
  // status dots: WiFi, Bluetooth, mic
  tft.fillCircle(262, 15, 5, WiFi.status() == WL_CONNECTED ? C_UP : C_DN);
  tft.fillCircle(281, 15, 5, audio.btConnected ? 0x041F : (audio.linked ? C_DIM : C_BAR));
  uint16_t mic = voiceState == V_OFF ? C_BAR : (voiceState == V_CONNECTING ? C_DIM : (voiceState == V_WAKE || voiceState == V_IDLE) ? 0xFFE0 : C_VOICE);
  tft.fillCircle(300, 15, 5, mic);
  tft.fillRect(0, 228, 320, 12, C_BG);
  for (int i = 0; i < P_COUNT; i++) tft.fillCircle(128 + i * 16, 233, 3, i == page ? C_ACC : C_DIM);
  tft.setTextDatum(TL_DATUM);
}

void drawHome(const tm& t) {
  drawHeader("Today");
  char buf[40];
  strftime(buf, sizeof(buf), "%A", &t);
  tft.setTextColor(TFT_WHITE, C_BG); tft.drawString(buf, 12, 42, 4);
  strftime(buf, sizeof(buf), "%B %d, %Y", &t);
  tft.setTextColor(C_DIM, C_BG); tft.drawString(buf, 12, 72, 2);
  Weather w; xSemaphoreTake(dataLock, portMAX_DELAY); w = weather; xSemaphoreGive(dataLock);
  if (w.ok) {
    tft.setTextColor(C_ACC, C_BG);
    String tmp = String((int)round(w.temp));
    tft.drawString(tmp, 12, 100, 7);
    tft.drawString(cfg.fahrenheit ? "F" : "C", 18 + tft.textWidth(tmp, 7), 102, 4);
    tft.setTextColor(TFT_WHITE, C_BG); tft.drawString(weatherText(w.code), 150, 108, 4);
    snprintf(buf, sizeof(buf), "High %d  Low %d", (int)round(w.hi), (int)round(w.lo));
    tft.setTextColor(C_DIM, C_BG); tft.drawString(buf, 150, 140, 2);
  } else {
    tft.setTextColor(C_DIM, C_BG); tft.drawString("Weather: waiting for WiFi...", 12, 110, 2);
  }
  tft.setTextColor(TFT_WHITE, C_BG);
  String al = "Alarms: ";
  for (int i = 0; i < 2; i++) al += String(i ? "   " : "") + (cfg.alarm[i].on ? fmtTime(cfg.alarm[i].hour, cfg.alarm[i].minute) : String("off"));
  tft.drawString(al, 12, 172, 2);
  tft.setTextColor(C_DIM, C_BG);
  if (WiFi.status() == WL_CONNECTED) tft.drawString("http://hackclock.local  (" + WiFi.localIP().toString() + ")", 12, 194, 2);
  else if (portalRunning) tft.drawString("Join WiFi 'HackClock-Setup' to connect", 12, 194, 2);
  String vs = voiceState == V_OFF ? (cfg.haToken.length() ? "Voice: offline" : "Voice: add HA token on web page")
            : (cfg.wakeWord ? "Voice: say your wake word, or press TALK" : "Voice: press TALK");
  tft.drawString(vs, 12, 210, 1);
  tft.drawString("ntfy: " + cfg.ntfyTopic, 200, 210, 1);
}

void drawMusic() {
  drawHeader("Now playing");
  if (!audio.linked) { drawWrapped("Audio board not found. Check the 4-wire AUDIO link (5V, GND, SDA, SCL).", 12, 50, 296, 2, 22, 5, C_DIM); return; }
  if (!audio.btConnected) {
    drawWrapped("Open Bluetooth on your phone and connect to \"HackClock\". Then play anything!", 12, 50, 296, 4, 28, 5, TFT_WHITE);
    return;
  }
  // record icon
  tft.fillCircle(52, 90, 38, 0x2104); tft.drawCircle(52, 90, 30, 0x4208); tft.drawCircle(52, 90, 22, 0x4208);
  tft.fillCircle(52, 90, 9, C_ACC);
  String title = audio.title.length() ? audio.title : String("Bluetooth audio");
  drawWrapped(title, 104, 52, 206, 4, 27, 3, TFT_WHITE);
  tft.setTextColor(C_DIM, C_BG); tft.drawString(audio.artist, 104, 140, 2);
  tft.setTextColor(audio.playing ? C_UP : C_DIM, C_BG);
  tft.drawString(audio.playing ? "Playing" : "Paused", 12, 150, 2);
  // volume bar
  tft.setTextColor(C_DIM, C_BG); tft.drawString("Vol", 12, 190, 2);
  for (int i = 0; i < 10; i++) tft.fillRoundRect(46 + i * 26, 190, 22, 14, 3, i < cfg.volume ? C_ACC : 0x2104);
  tft.drawString("volume: phone / web page / voice   hold spoiler = play/pause", 12, 212, 1);
}

void drawStocks() {
  drawHeader("Markets");
  if (cfg.finnhub.isEmpty()) { drawWrapped("Add a free Finnhub API key on http://hackclock.local to see live quotes.", 12, 50, 296, 4, 28, 5, TFT_WHITE); return; }
  Quote q[6]; int n;
  xSemaphoreTake(dataLock, portMAX_DELAY); n = quoteCount; for (int i = 0; i < n; i++) q[i] = quotes[i]; xSemaphoreGive(dataLock);
  if (n == 0) { drawWrapped("Loading quotes...", 12, 60, 296, 4, 28, 2, C_DIM); return; }
  for (int i = 0; i < n; i++) {
    int y = 38 + i * 31;
    tft.setTextColor(TFT_WHITE, C_BG); tft.setTextDatum(TL_DATUM); tft.drawString(q[i].sym, 12, y, 4);
    if (!q[i].ok) { tft.setTextColor(C_DIM, C_BG); tft.drawString("n/a", 120, y, 4); continue; }
    uint16_t col = q[i].change >= 0 ? C_UP : C_DN;
    tft.setTextDatum(TR_DATUM);
    tft.setTextColor(TFT_WHITE, C_BG); tft.drawString(String(q[i].price, 2), 210, y, 4);
    tft.setTextColor(col, C_BG);
    char b[16]; snprintf(b, sizeof(b), "%+.2f%%", q[i].pct); tft.drawString(b, 308, y + 4, 2);
    int ax = 222, ay = y + 12;
    if (q[i].change >= 0) tft.fillTriangle(ax, ay + 5, ax + 10, ay + 5, ax + 5, ay - 5, col);
    else                  tft.fillTriangle(ax, ay - 5, ax + 10, ay - 5, ax + 5, ay + 5, col);
    tft.setTextDatum(TL_DATUM);
  }
}

void drawNews() {
  drawHeader("News");
  String h; int n;
  xSemaphoreTake(dataLock, portMAX_DELAY); n = headlineCount; if (n) h = headlines[newsIdx % n]; xSemaphoreGive(dataLock);
  if (!n) { drawWrapped("Loading headlines...", 12, 60, 296, 4, 28, 2, C_DIM); return; }
  tft.setTextColor(C_ACC, C_BG); tft.drawString(String(newsIdx % n + 1) + " / " + String(n), 12, 40, 2);
  drawWrapped(h, 12, 62, 296, 4, 30, 5, TFT_WHITE);
}

void drawMessage() {
  drawHeader("Messages");
  Message m; xSemaphoreTake(dataLock, portMAX_DELAY); m = lastMsg; lastMsg.unread = false; xSemaphoreGive(dataLock);
  if (m.text.isEmpty()) { drawWrapped("No messages yet. Send one with the ntfy app to topic:\n" + cfg.ntfyTopic, 12, 50, 296, 2, 22, 6, C_DIM); return; }
  tft.setTextColor(C_ACC, C_BG); tft.drawString(m.title, 12, 40, 4);
  struct tm mt; localtime_r(&m.when, &mt);
  tft.setTextColor(C_DIM, C_BG); tft.drawString("at " + fmtTime(mt.tm_hour, mt.tm_min), 12, 68, 2);
  drawWrapped(m.text, 12, 92, 296, 4, 28, 4, TFT_WHITE);
}

void drawVoicePanel() {
  const int y0 = 128;
  tft.fillRoundRect(4, y0, 312, 98, 10, 0x10A6);
  tft.drawRoundRect(4, y0, 312, 98, 10, C_VOICE);
  const char* st = voiceState == V_LISTEN ? "Listening..." : voiceState == V_THINK ? "Thinking..." :
                   voiceState == V_SPEAK ? "Speaking" : "Assistant";
  tft.fillCircle(22, y0 + 16, 7, voiceState == V_LISTEN ? C_DN : C_VOICE);
  tft.setTextColor(C_VOICE, 0x10A6); tft.drawString(st, 36, y0 + 8, 2);
  String heard, reply;
  xSemaphoreTake(dataLock, portMAX_DELAY); heard = voiceHeard; reply = voiceReply; xSemaphoreGive(dataLock);
  int used = 0;
  if (heard.length() && voiceState != V_LISTEN) used = drawWrapped("\"" + heard + "\"", 14, y0 + 28, 292, 2, 17, 2, C_DIM, 0x10A6);
  if (reply.length() && voiceState != V_LISTEN) drawWrapped(reply, 14, y0 + 30 + used * 17, 292, 2, 17, 4 - used, TFT_WHITE, 0x10A6);
}

void drawEdit() {
  tft.fillScreen(C_BG);
  tft.setTextColor(C_ACC, C_BG); tft.drawString("Set alarm " + String(editAlarm + 1), 12, 12, 4);
  Alarm& a = cfg.alarm[editAlarm];
  const char* labels[] = {"Alarm", "Hour", "Minute", "On/Off", "Days"};
  String values[] = { String(editAlarm + 1), String(a.hour), String(a.minute < 10 ? "0" : "") + String(a.minute),
                      String(a.on ? "ON" : "OFF"), daysText(a.days) };
  for (int i = 0; i < 5; i++) {
    int y = 52 + i * 32; bool sel = (i == editField);
    if (sel) tft.fillRoundRect(6, y - 4, 308, 30, 6, 0x2945);
    tft.setTextColor(sel ? C_ACC : C_DIM, sel ? 0x2945 : C_BG); tft.drawString(labels[i], 16, y, 4);
    tft.setTextColor(TFT_WHITE, sel ? 0x2945 : C_BG); tft.setTextDatum(TR_DATUM);
    tft.drawString(values[i], 300, y, 4); tft.setTextDatum(TL_DATUM);
  }
  tft.setTextColor(C_DIM, C_BG); tft.drawString("UP/DOWN change   MODE next   SNOOZE cancel", 12, 220, 2);
}

void drawRinging() {
  tft.fillScreen(0xA000);
  tft.setTextColor(TFT_WHITE, 0xA000); tft.setTextDatum(MC_DATUM);
  tft.drawString(ringIsTimer ? "TIME'S UP!" : "WAKE UP!", 160, 80, 4);
  time_t now = time(nullptr); struct tm t; localtime_r(&now, &t);
  tft.drawString(fmtTime(t.tm_hour, t.tm_min), 160, 120, 4);
  tft.drawString(ringIsTimer ? "any button = stop" : "slap the spoiler = stop   MODE = snooze 9 min   or say \"stop\"", 160, 180, 2);
  tft.setTextDatum(TL_DATUM);
}

void redraw(const tm& t) {
  if (ringing) { drawRinging(); return; }
  if (editing) { drawEdit(); return; }
  tft.fillRect(0, 30, 320, 198, C_BG);
  switch (page) {
    case P_HOME:   drawHome(t);   break;
    case P_MUSIC:  drawMusic();   break;
    case P_STOCKS: drawStocks();  break;
    case P_NEWS:   drawNews();    break;
    case P_MSG:    drawMessage(); break;
    default: break;
  }
  if (voicePanel) drawVoicePanel();
}

// ------------------------------------------------------------------ 7-segment (HT16K33)
void updateSegments(const tm& t, bool night) {
  static uint32_t last = 0;
  static String lastShown;
  if (!segOk || millis() - last < 100) return;
  last = millis();
  bool blink = (millis() / 500) % 2;
  uint8_t bri = (night || forceNight) ? 0 : cfg.brightness * 2 + 1;
  int d[4] = {-1, -1, -1, -1}; bool colon = false; bool dashes = false;

  if (editing) {
    Alarm& a = cfg.alarm[editAlarm];
    d[0] = a.hour / 10; d[1] = a.hour % 10; d[2] = a.minute / 10; d[3] = a.minute % 10; colon = true;
    if (blink && editField == 1) d[0] = d[1] = -1;
    if (blink && editField == 2) d[2] = d[3] = -1;
  } else if (!timeValid()) {
    dashes = true;
  } else if (ringing && !blink) {
    // all off while flashing
  } else {
    int h = t.tm_hour;
    if (!cfg.h24) { h %= 12; if (h == 0) h = 12; }
    d[0] = (cfg.h24 || h >= 10) ? h / 10 : -1; d[1] = h % 10; d[2] = t.tm_min / 10; d[3] = t.tm_min % 10;
    colon = ringing ? true : (t.tm_sec % 2 == 0);
  }
  char key[24]; snprintf(key, sizeof(key), "%d%d%d%d%d%d%d", d[0], d[1], d[2], d[3], colon, dashes, bri);
  if (lastShown == key) return;
  lastShown = key;
  seg.setBrightness(bri);
  const uint8_t pos[4] = {0, 1, 3, 4};               // position 2 is the colon
  for (int i = 0; i < 4; i++) {
    if (dashes) seg.writeDigitRaw(pos[i], 0x40);
    else if (d[i] < 0) seg.writeDigitRaw(pos[i], 0x00);
    else seg.writeDigitNum(pos[i], d[i], false);
  }
  seg.drawColon(colon);
  seg.writeDisplay();
}

// ------------------------------------------------------------------ web server
String checked(bool b) { return b ? " checked" : ""; }

void handleRoot() {
  String html = FPSTR(PAGE_HEAD);
  html += "<h1>HackClock</h1><form method='POST' action='/save'>";
  for (int i = 0; i < 2; i++) {
    Alarm& a = cfg.alarm[i]; String n = String(i);
    char tbuf[6]; snprintf(tbuf, sizeof(tbuf), "%02d:%02d", a.hour, a.minute);
    html += "<fieldset><legend>Alarm " + String(i + 1) + "</legend>";
    html += "<label><input type='checkbox' name='on" + n + "'" + checked(a.on) + "> enabled</label>";
    html += "<input type='time' name='t" + n + "' value='" + tbuf + "'><div class='days'>";
    const char* dn[] = {"Su","Mo","Tu","We","Th","Fr","Sa"};
    for (int d = 0; d < 7; d++)
      html += "<label><input type='checkbox' name='d" + n + String(d) + "'" + checked(a.days & (1 << d)) + ">" + dn[d] + "</label>";
    html += "</div></fieldset>";
  }
  html += "<fieldset><legend>Voice assistant (Home Assistant)</legend>";
  html += "<label>Home Assistant host or IP<input name='haH' value='" + cfg.haHost + "'></label>";
  html += "<label>Port<input type='number' name='haP' value='" + String(cfg.haPort) + "'></label>";
  html += "<label>Long-lived access token<input type='password' name='haT' placeholder='" +
          String(cfg.haToken.length() ? "(saved - leave blank to keep)" : "paste token") + "'></label>";
  html += "<label><input type='checkbox' name='wake'" + checked(cfg.wakeWord) + "> Listen for wake word (otherwise TALK button only)</label></fieldset>";
  html += "<fieldset><legend>Speaker</legend>";
  html += "<label>Volume 0-10<input type='number' min='0' max='10' name='vol' value='" + String(cfg.volume) + "'></label>";
  html += "<label><input type='checkbox' name='aSpk'" + checked(cfg.alarmSpeaker) + "> Alarm through the speaker (buzzers if off)</label></fieldset>";
  html += "<fieldset><legend>Info sources</legend>";
  html += "<label>Stock symbols (max 6)<input name='sym' value='" + cfg.symbols + "'></label>";
  html += "<label>Finnhub API key (free at finnhub.io)<input name='fh' value='" + cfg.finnhub + "'></label>";
  html += "<label>News RSS feed URL<input name='rss' value='" + cfg.rssUrl + "'></label>";
  html += "<label>ntfy topic for phone messages<input name='ntfy' value='" + cfg.ntfyTopic + "'></label>";
  html += "<label>Latitude<input name='lat' value='" + String(cfg.lat, 4) + "'></label>";
  html += "<label>Longitude<input name='lon' value='" + String(cfg.lon, 4) + "'></label>";
  html += "<label><input type='checkbox' name='degF'" + checked(cfg.fahrenheit) + "> Fahrenheit</label></fieldset>";
  html += "<fieldset><legend>Display</legend>";
  html += "<label>Time zone (POSIX)<input name='tz' value='" + cfg.tz + "'></label>";
  html += "<label><input type='checkbox' name='h24'" + checked(cfg.h24) + "> 24-hour clock</label>";
  html += "<label>Brightness 0-7<input type='number' min='0' max='7' name='bri' value='" + String(cfg.brightness) + "'></label>";
  html += "<label>Night dim from hour<input type='number' min='0' max='23' name='nS' value='" + String(cfg.nightStart) + "'></label>";
  html += "<label>Night dim until hour<input type='number' min='0' max='23' name='nE' value='" + String(cfg.nightEnd) + "'></label>";
  html += "<label>Seconds per page<input type='number' min='4' max='120' name='pgs' value='" + String(cfg.pageSeconds) + "'></label>";
  html += "</fieldset><button>Save</button></form>";
  html += "<form method='POST' action='/msg'><fieldset><legend>Send a message to the clock</legend>"
          "<input name='text' placeholder='Dinner is ready!'><button>Send</button></fieldset></form>";
  html += "<p><a href='/talk'>Talk</a> &middot; <a href='/snooze'>Snooze</a> &middot; <a href='/stop'>Stop alarm</a></p>";
  html += FPSTR(PAGE_TAIL);
  server.send(200, "text/html", html);
}

void handleSave() {
  for (int i = 0; i < 2; i++) {
    String n = String(i);
    cfg.alarm[i].on = server.hasArg("on" + n);
    String t = server.arg("t" + n);
    if (t.length() >= 5) { cfg.alarm[i].hour = t.substring(0, 2).toInt(); cfg.alarm[i].minute = t.substring(3, 5).toInt(); }
    uint8_t d = 0;
    for (int k = 0; k < 7; k++) if (server.hasArg("d" + n + String(k))) d |= 1 << k;
    cfg.alarm[i].days = d ? d : 0x7F;
    cfg.alarm[i].oneShot = false;
  }
  bool voiceChanged = server.arg("haH") != cfg.haHost || server.arg("haP").toInt() != cfg.haPort || server.arg("haT").length() > 0;
  cfg.haHost = server.arg("haH"); cfg.haHost.trim();
  cfg.haPort = server.arg("haP").toInt() ? server.arg("haP").toInt() : 8123;
  if (server.arg("haT").length() > 10) { cfg.haToken = server.arg("haT"); cfg.haToken.trim(); }
  cfg.wakeWord = server.hasArg("wake");
  cfg.volume = constrain(server.arg("vol").toInt(), 0, 10);
  cfg.alarmSpeaker = server.hasArg("aSpk");
  cfg.symbols   = server.arg("sym");
  cfg.finnhub   = server.arg("fh");   cfg.finnhub.trim();
  cfg.rssUrl    = server.arg("rss");  cfg.rssUrl.trim();
  if (server.arg("ntfy").length() > 3) { cfg.ntfyTopic = server.arg("ntfy"); cfg.ntfyTopic.trim(); }
  cfg.lat = server.arg("lat").toFloat(); cfg.lon = server.arg("lon").toFloat();
  cfg.fahrenheit = server.hasArg("degF");
  cfg.tz  = server.arg("tz"); cfg.h24 = server.hasArg("h24");
  cfg.brightness  = constrain(server.arg("bri").toInt(), 0, 7);
  cfg.nightStart  = constrain(server.arg("nS").toInt(), 0, 23);
  cfg.nightEnd    = constrain(server.arg("nE").toInt(), 0, 23);
  cfg.pageSeconds = constrain(server.arg("pgs").toInt(), 4, 120);
  saveSettings();
  setenv("TZ", cfg.tz.c_str(), 1); tzset();
  audioCmd(AC_VOLUME, cfg.volume);
  if (voiceChanged) voiceRestart();
  refetchAll = true; needRedraw = true;
  server.sendHeader("Location", "/"); server.send(303);
}

void handleMsg() {
  Message m; m.title = "Message"; m.text = server.arg("text"); m.when = time(nullptr); m.unread = true;
  if (m.text.length()) { xSemaphoreTake(dataLock, portMAX_DELAY); lastMsg = m; xSemaphoreGive(dataLock); newMessageFlag = true; }
  server.sendHeader("Location", "/"); server.send(303);
}

void startServer() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/save", HTTP_POST, handleSave);
  server.on("/msg", HTTP_POST, handleMsg);
  server.on("/talk",   []() { voiceTalk();             server.sendHeader("Location", "/"); server.send(303); });
  server.on("/snooze", []() { if (ringing) snooze();   server.sendHeader("Location", "/"); server.send(303); });
  server.on("/stop",   []() { dismiss();               server.sendHeader("Location", "/"); server.send(303); });
  server.begin();
  MDNS.begin("hackclock");
  MDNS.addService("http", "tcp", 80);
  serverStarted = true;
}

// ------------------------------------------------------------------ actions
void setVolume(int v) { cfg.volume = constrain(v, 0, 10); audioCmd(AC_VOLUME, cfg.volume); saveSettings(); if (page == P_MUSIC) needRedraw = true; }

void runAction(const Action& x) {
  switch (x.type) {
    case A_SNOOZE:  if (ringing) snooze(); break;
    case A_DISMISS: dismiss(); break;
    case A_SET_ALARM:                                  // voice alarms use slot 2 as a one-time alarm
      cfg.alarm[1].hour = x.a; cfg.alarm[1].minute = x.b; cfg.alarm[1].on = true;
      cfg.alarm[1].days = 0x7F; cfg.alarm[1].oneShot = true; saveSettings(); break;
    case A_ALARM_OFF: cfg.alarm[0].on = cfg.alarm[1].on = false; snoozeUntil = 0; saveSettings(); break;
    case A_TIMER:   timerEnd = time(nullptr) + x.a; break;
    case A_TIMER_CANCEL: timerEnd = 0; break;
    case A_PLAY:  audioCmd(AC_PLAY); break;
    case A_PAUSE: audioCmd(AC_PAUSE); break;
    case A_NEXT:  audioCmd(AC_NEXT); break;
    case A_PREV:  audioCmd(AC_PREV); break;
    case A_VOLUME: setVolume(x.a); break;
    case A_NIGHT: forceNight = !forceNight; break;
    case A_PAGE:  page = (Page)constrain(x.a, 0, P_COUNT - 1); pageSince = millis(); manualUntil = millis() + 60000; break;
  }
  needRedraw = true;
}

void onButton(Btn b, Evt e) {
  if (ringing) {
    if (e == E_SHORT || e == E_LONG) { if (b == B_MODE) snooze(); else dismiss(); }     // spoiler (SNOOZE input) and TALK stop it, MODE snoozes 9 min
    return;
  }
  if (editing) {
    Alarm& a = cfg.alarm[editAlarm];
    int dir = (b == B_UP) ? 1 : (b == B_DOWN) ? -1 : 0;
    if (dir && (e == E_SHORT || e == E_REPEAT)) {
      switch (editField) {
        case 0: editAlarm ^= 1; break;
        case 1: a.hour = (a.hour + 24 + dir) % 24; break;
        case 2: a.minute = (a.minute + 60 + dir) % 60; break;
        case 3: a.on = !a.on; break;
        case 4: { const uint8_t presets[] = {0x7F, 0x3E, 0x41};
                  int idx = 0; for (int i = 0; i < 3; i++) if (presets[i] == a.days) idx = i;
                  a.days = presets[(idx + 3 + dir) % 3]; } break;
      }
      a.oneShot = false;
      needRedraw = true;
    } else if (b == B_MODE && e == E_SHORT) {
      if (++editField > 4) { editing = false; saveSettings(); }
      needRedraw = true;
    } else if (b == B_SNOOZE && e == E_SHORT) {
      editing = false; loadSettings(); needRedraw = true;
    }
    return;
  }
  if (b == B_TALK && e == E_SHORT)  { voiceTalk(); }
  if (b == B_TALK && e == E_LONG)   { cfg.wakeWord = !cfg.wakeWord; saveSettings(); voiceDirty = true; chime(); }
  if (b == B_MODE && e == E_SHORT)  { page = (Page)((page + 1) % P_COUNT); pageSince = millis(); manualUntil = millis() + 60000; needRedraw = true; }
  if (b == B_MODE && e == E_LONG)   { cfg.brightness = (cfg.brightness + 1) & 7; saveSettings(); needRedraw = true; }     // hold MODE: step the brightness
  if (b == B_SNOOZE && e == E_SHORT) forceNight = !forceNight;
  if (b == B_SNOOZE && e == E_LONG) {
    if (snoozeUntil) { snoozeUntil = 0; needRedraw = true; }
    else if (audio.btConnected) audioCmd(audio.playing ? AC_PAUSE : AC_PLAY);
  }
  if (b == B_MODE && e == E_VLONG) {                          // hold MODE for 8 s: forget the WiFi
    tft.fillScreen(C_BG); tft.setTextColor(TFT_WHITE, C_BG); tft.drawString("Resetting WiFi...", 12, 100, 4);
    wm.resetSettings(); delay(500); ESP.restart();
  }
}

// ------------------------------------------------------------------ setup / loop
void setup() {
  Serial.begin(115200);
  dataLock = xSemaphoreCreateMutex();
  actionQueue = xQueueCreate(8, sizeof(Action));
  loadSettings();
  setenv("TZ", cfg.tz.c_str(), 1); tzset();

  ledcAttachPin(PIN_BUZZER, LEDC_BUZZ); ledcWriteTone(LEDC_BUZZ, 0);
  analogSetPinAttenuation(PIN_BUTTONS, ADC_11db);

  tft.init(); tft.setRotation(1); tft.fillScreen(C_BG);
  tft.setTextColor(C_ACC, C_BG); tft.drawString("HackClock", 12, 80, 4);
  tft.setTextColor(C_DIM, C_BG); tft.drawString("starting up...", 12, 115, 2);

  Wire.begin(PIN_SDA, PIN_SCL, 100000);
  segOk = seg.begin(I2C_ADDR_SEG);
  if (segOk) { seg.setBrightness(cfg.brightness * 2 + 1); for (int p : {0, 1, 3, 4}) seg.writeDigitRaw(p, 0x40); seg.writeDisplay(); }
  rtcOk = rtc.begin();
  if (rtcOk && !rtc.lostPower()) { struct timeval tv = { (time_t)rtc.now().unixtime(), 0 }; settimeofday(&tv, nullptr); }
  audioBegin();

  WiFi.mode(WIFI_STA);
  wm.setConfigPortalBlocking(false);
  wm.setConfigPortalTimeout(0);
  tft.drawString("Connecting to WiFi (or join 'HackClock-Setup')", 12, 140, 2);
  if (wm.autoConnect("HackClock-Setup")) startServer(); else portalRunning = true;

  sntp_set_time_sync_notification_cb(onNtpSync);
  configTzTime(cfg.tz.c_str(), "pool.ntp.org", "time.nist.gov");

  xTaskCreatePinnedToCore(netTask,   "net",   12288, nullptr, 1, nullptr, 0);
  xTaskCreatePinnedToCore(voiceTask, "voice", 16384, nullptr, 2, nullptr, 0);
  playTune(chimeTune, 5, false);
  pageSince = millis();
}

void loop() {
  if (portalRunning) {
    wm.process();
    if (WiFi.status() == WL_CONNECTED) { portalRunning = false; startServer(); configTzTime(cfg.tz.c_str(), "pool.ntp.org"); needRedraw = true; }
  }
  if (serverStarted) server.handleClient();
  if (ntpSynced) { ntpSynced = false; if (rtcOk) rtc.adjust(DateTime((uint32_t)time(nullptr))); }

  audioPoll();
  if (voiceHoldRequest >= 0) { audioCmd(AC_HOLD, voiceHoldRequest); voiceHoldRequest = -1; }
  if (voiceBeepRequest) { voiceBeepRequest = false; if (audio.linked) audioCmd(AC_LISTEN_BEEP); else playTune(beepTune, 1, false); }
  Action x; while (xQueueReceive(actionQueue, &x, 0) == pdTRUE) runAction(x);

  time_t now = time(nullptr);
  struct tm t; localtime_r(&now, &t);
  bool night = isNight(t) && timeValid();

  if (timeValid()) checkAlarms(t);
  serviceBuzzer();
  updateSegments(t, night);

  Btn b; Evt e = pollButtons(b);
  if (e != E_NONE) onButton(b, e);

  if (newMessageFlag) {
    newMessageFlag = false;
    if (!ringing && !editing) { page = P_MSG; pageSince = millis(); manualUntil = millis() + 60000; needRedraw = true; if (!night) chime(); }
  }

  // jump to "Now playing" when music starts
  static bool lastPlaying = false;
  if (audio.playing != lastPlaying) {
    lastPlaying = audio.playing;
    if (audio.playing && !editing && !ringing) { page = P_MUSIC; pageSince = millis(); manualUntil = millis() + 20000; }
    needRedraw = true;
  }

  // voice panel overlay
  static VoiceState lastVs = V_OFF;
  if (voiceDirty || voiceState != lastVs) {
    voiceDirty = false;
    bool active = voiceState == V_LISTEN || voiceState == V_THINK || voiceState == V_SPEAK;
    if (active) { voicePanel = true; replyShownAt = millis(); }
    else if (lastVs == V_SPEAK || lastVs == V_THINK) replyShownAt = millis();   // keep the answer up a bit
    lastVs = voiceState;
    needRedraw = true;
  }
  if (voicePanel && !(voiceState == V_LISTEN || voiceState == V_THINK || voiceState == V_SPEAK) && millis() - replyShownAt > 8000) {
    voicePanel = false; needRedraw = true;
  }

  // page rotation (skip pages with nothing to show)
  if (!editing && !ringing && !voicePanel && millis() > manualUntil && millis() - pageSince > cfg.pageSeconds * 1000UL) {
    for (int i = 0; i < P_COUNT; i++) {
      page = (Page)((page + 1) % P_COUNT);
      bool skip = (page == P_MUSIC && !audio.btConnected) || (page == P_MSG && lastMsg.text.isEmpty());
      if (!skip) break;
    }
    pageSince = millis(); needRedraw = true;
  }
  if (page == P_NEWS && millis() - newsSince > 6000) { newsIdx++; newsSince = millis(); needRedraw = true; }

  static bool lastRinging = false;
  if (ringing != lastRinging) { lastRinging = ringing; needRedraw = true; }
  static int lastMin = -1;
  if (t.tm_min != lastMin) { lastMin = t.tm_min; needRedraw = true; }
  static int lastTimerSec = -1;
  if (timerEnd && (int)(now % 60) != lastTimerSec) { lastTimerSec = now % 60; tft.fillRect(170, 0, 84, 30, C_BAR); drawHeader(page == P_HOME ? "Today" : page == P_MUSIC ? "Now playing" : page == P_STOCKS ? "Markets" : page == P_NEWS ? "News" : "Messages"); }
  if (dataDirty) { dataDirty = false; needRedraw = true; }

  // backlight (driven by the audio board)
  static int lastDuty = -1;
  int duty = ((night || forceNight) && !ringing && !voicePanel) ? 6 : map(cfg.brightness, 0, 7, 25, 255);
  if (duty != lastDuty && audio.linked) { audioCmd(AC_BACKLIGHT, duty); lastDuty = duty; }
  if (!audio.linked) lastDuty = -1;

  if (needRedraw) { needRedraw = false; redraw(t); }
  delay(5);
}
