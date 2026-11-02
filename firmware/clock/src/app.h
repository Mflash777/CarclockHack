#pragma once
// Shared declarations for the HackClock clock firmware (XIAO ESP32-S3)
#include <Arduino.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"

// ------------------------------------------------------------------ settings
struct Alarm {
  uint8_t hour = 7, minute = 0;
  bool    on = false;
  uint8_t days = 0x7F;               // bit0 = Sunday ... bit6 = Saturday
  bool    oneShot = false;           // set by voice: turns itself off after ringing
};

struct Settings {
  String  tz        = "EST5EDT,M3.2.0,M11.1.0";
  bool    h24       = false;
  Alarm   alarm[2];
  String  symbols   = "AAPL,MSFT,NVDA,TSLA,SPY,AMZN";
  String  finnhub   = "";
  String  ntfyTopic = "";
  String  rssUrl    = "https://feeds.bbci.co.uk/news/world/rss.xml";
  float   lat = 34.02f, lon = -84.55f;
  bool    fahrenheit = true;
  uint8_t nightStart = 22, nightEnd = 7;
  uint8_t brightness = 5;            // 0..7
  uint8_t pageSeconds = 12;
  // v2: voice + speaker
  String  haHost    = "homeassistant.local";
  uint16_t haPort   = 8123;
  String  haToken   = "";            // long-lived access token from your HA profile page
  bool    wakeWord  = true;          // stream to HA's wake-word engine when idle
  uint8_t volume    = 6;             // 0..10
  bool    alarmSpeaker = true;       // alarm through the speaker (buzzers are the fallback)
};
extern Settings cfg;
void loadSettings();
void saveSettings();

// ------------------------------------------------------------------ fetched data
struct Quote   { String sym; float price = 0, change = 0, pct = 0; bool ok = false; };
struct Weather { bool ok = false; float temp = 0, hi = 0, lo = 0; int code = 0; };
struct Message { String title, text; time_t when = 0; bool unread = false; };

extern SemaphoreHandle_t dataLock;
extern Weather weather;
extern Quote   quotes[6];
extern int     quoteCount;
extern String  headlines[8];
extern int     headlineCount;
extern Message lastMsg;
extern volatile bool dataDirty, newMessageFlag, refetchAll;
void netTask(void*);
const char* weatherText(int code);
String fmtTime(int h, int m);
String fmtTimeSpoken(int h, int m);

// ------------------------------------------------------------------ audio board link (I2C)
enum AudioCmd : uint8_t {
  AC_WIFI_SSID = 0x01, AC_WIFI_PASS = 0x02, AC_WIFI_GO = 0x03,
  AC_URL_CLEAR = 0x10, AC_URL_APPEND = 0x11, AC_URL_PLAY = 0x12, AC_STOP_TTS = 0x13,
  AC_PLAY = 0x20, AC_PAUSE = 0x21, AC_NEXT = 0x22, AC_PREV = 0x23, AC_VOLUME = 0x24,
  AC_TONE_ALARM = 0x30, AC_TONE_STOP = 0x31, AC_CHIME = 0x32, AC_LISTEN_BEEP = 0x33,
  AC_BACKLIGHT = 0x40, AC_HOLD = 0x50,   // payload 1 = pause music while we listen, 0 = resume
};
struct AudioStatus {
  bool linked = false;               // got a valid status in the last few seconds
  bool btConnected = false, playing = false, ttsPlaying = false, toneActive = false, wifi = false;
  uint8_t volume = 0, seq = 0;
  String title, artist;
};
extern AudioStatus audio;            // updated by the main loop only
extern volatile bool audioTtsBusy;   // mirror for the voice task
void audioBegin();
void audioPoll();                    // call from loop()
void audioCmd(uint8_t cmd, int value = -1);
void audioQueueUrl(const String& url);   // safe from any task

// ------------------------------------------------------------------ voice (Home Assistant Assist)
enum VoiceState : uint8_t { V_OFF, V_CONNECTING, V_IDLE, V_WAKE, V_LISTEN, V_THINK, V_SPEAK };
extern volatile VoiceState voiceState;
extern volatile bool voiceDirty;
extern String voiceHeard, voiceReply;     // protected by dataLock
void voiceTask(void*);
void voiceTalk();                         // push-to-talk request (any task)
void voiceRestart();                      // settings changed

// ------------------------------------------------------------------ actions from voice -> main loop
enum ActType : uint8_t { A_SNOOZE, A_DISMISS, A_SET_ALARM, A_ALARM_OFF, A_TIMER, A_TIMER_CANCEL,
                         A_PLAY, A_PAUSE, A_NEXT, A_PREV, A_VOLUME, A_NIGHT, A_PAGE };
struct Action { ActType type; int a = 0, b = 0; };
extern QueueHandle_t actionQueue;
bool handleLocalCommand(const String& text, String& reply);   // voice task

// state the command parser reads (main loop owns it)
extern volatile bool ringing;
extern volatile time_t timerEnd;
