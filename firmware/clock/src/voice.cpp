// Voice assistant via Home Assistant "Assist" pipelines (WebSocket API).
//
// Flow:  mic (INMP441, 16 kHz) --> HA wake word (openWakeWord) --> HA speech-to-text (Whisper/Cloud)
//        --> text handled here (alarms, timers, music, weather...) or sent to HA's conversation agent
//        --> HA text-to-speech (Piper/Cloud) --> URL handed to the audio board, which plays it.
//
// HA websocket messages used:
//   {"type":"auth","access_token":...}
//   {"id":N,"type":"assist_pipeline/run","start_stage":"wake_word|stt|intent|tts","end_stage":"stt|tts","input":{...}}
//   binary frames: [stt_binary_handler_id][16-bit PCM little-endian...], a single [handler_id] byte = end of audio
#include "app.h"
#include "pins.h"
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <driver/i2s.h>

volatile VoiceState voiceState = V_OFF;
volatile bool voiceDirty = false;
String voiceHeard, voiceReply;
volatile int  voiceHoldRequest = -1;     // main loop forwards to the audio board: 1 = pause music, 0 = resume
volatile bool voiceBeepRequest = false;  // main loop plays the "listening" beep

enum RunKind { RUN_NONE, RUN_WAKE, RUN_STT, RUN_INTENT, RUN_TTS };

static WebSocketsClient ws;
static bool wsStarted = false, authed = false;
static int  msgId = 1, runId = -1, handlerId = -1;
static RunKind runKind = RUN_NONE;
static bool streaming = false, runEnded = false, runFailed = false, sttDone = false, wakeHeard = false;
static String heardText, replyText, ttsUrl, lastError;
static uint32_t stateSince = 0, runStarted = 0, nextWakeAt = 0;
static volatile bool talkRequested = false, restartRequested = false;
static bool holding = false;

void voiceTalk()    { talkRequested = true; }
void voiceRestart() { restartRequested = true; }

static void setState(VoiceState s) { voiceState = s; stateSince = millis(); voiceDirty = true; }

static void hold(bool on) {
  if (on != holding) { holding = on; voiceHoldRequest = on ? 1 : 0; }
}

// ------------------------------------------------------------------ microphone
static void micBegin() {
  i2s_config_t c = {};
  c.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  c.sample_rate = 16000;
  c.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  c.channel_format = MIC_CHANNEL_FMT;
  c.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  c.intr_alloc_flags = 0;
  c.dma_buf_count = 6;
  c.dma_buf_len = 256;
  c.use_apll = false;
  i2s_pin_config_t p = {};
  p.mck_io_num = I2S_PIN_NO_CHANGE;
  p.bck_io_num = PIN_MIC_SCK;
  p.ws_io_num = PIN_MIC_WS;
  p.data_out_num = I2S_PIN_NO_CHANGE;
  p.data_in_num = PIN_MIC_SD;
  i2s_driver_install(I2S_NUM_0, &c, 0, nullptr);
  i2s_set_pin(I2S_NUM_0, &p);
}

// ------------------------------------------------------------------ websocket helpers
static void sendJson(JsonDocument& d) { String s; serializeJson(d, s); ws.sendTXT(s); }

static void endAudio() {
  if (handlerId >= 0 && streaming) { uint8_t b = (uint8_t)handlerId; ws.sendBIN(&b, 1); }
  streaming = false;
}

static void startRun(RunKind kind, const String& text = "") {
  JsonDocument d;
  runId = msgId++;
  runKind = kind;
  handlerId = -1; streaming = false;
  runEnded = runFailed = sttDone = wakeHeard = false;
  heardText = ""; ttsUrl = ""; replyText = ""; lastError = "";
  runStarted = millis();
  d["id"] = runId;
  d["type"] = "assist_pipeline/run";
  switch (kind) {
    case RUN_WAKE:
      d["start_stage"] = "wake_word"; d["end_stage"] = "stt";
      d["input"]["sample_rate"] = 16000;
      d["input"]["timeout"] = 3600;          // seconds to wait for the wake word
      break;
    case RUN_STT:
      d["start_stage"] = "stt"; d["end_stage"] = "stt";
      d["input"]["sample_rate"] = 16000;
      break;
    case RUN_INTENT:
      d["start_stage"] = "intent"; d["end_stage"] = "tts";
      d["input"]["text"] = text;
      break;
    case RUN_TTS:
      d["start_stage"] = "tts"; d["end_stage"] = "tts";
      d["input"]["text"] = text;
      break;
    default: break;
  }
  sendJson(d);
}

static void onText(uint8_t* payload, size_t len) {
  JsonDocument filter;
  filter["type"] = true; filter["id"] = true; filter["success"] = true;
  filter["error"]["message"] = true;
  filter["event"]["type"] = true;
  filter["event"]["data"]["runner_data"]["stt_binary_handler_id"] = true;
  filter["event"]["data"]["stt_output"]["text"] = true;
  filter["event"]["data"]["intent_output"]["response"]["speech"]["plain"]["speech"] = true;
  filter["event"]["data"]["tts_output"]["url"] = true;
  filter["event"]["data"]["code"] = true;
  filter["event"]["data"]["message"] = true;
  JsonDocument d;
  if (deserializeJson(d, (const char*)payload, len, DeserializationOption::Filter(filter))) return;
  const char* type = d["type"] | "";

  if (!strcmp(type, "auth_required")) {
    JsonDocument a; a["type"] = "auth"; a["access_token"] = cfg.haToken; sendJson(a); return;
  }
  if (!strcmp(type, "auth_ok"))      { authed = true; setState(V_IDLE); return; }
  if (!strcmp(type, "auth_invalid")) {
    authed = false; setState(V_OFF);
    xSemaphoreTake(dataLock, portMAX_DELAY); voiceReply = "Home Assistant rejected the token"; xSemaphoreGive(dataLock);
    return;
  }
  if ((d["id"] | -1) != runId) return;                 // events from an old run
  if (!strcmp(type, "result")) {
    if (!(d["success"] | false)) { runFailed = true; lastError = String((const char*)(d["error"]["message"] | "pipeline error")); }
    return;
  }
  if (strcmp(type, "event")) return;
  const char* et = d["event"]["type"] | "";
  JsonVariant data = d["event"]["data"];
  if (!strcmp(et, "run-start")) {
    handlerId = data["runner_data"]["stt_binary_handler_id"] | -1;
    streaming = (runKind == RUN_WAKE || runKind == RUN_STT) && handlerId >= 0;
  } else if (!strcmp(et, "wake_word-end")) {
    wakeHeard = true;
  } else if (!strcmp(et, "stt-end")) {
    heardText = String((const char*)(data["stt_output"]["text"] | ""));
    sttDone = true; streaming = false;
  } else if (!strcmp(et, "intent-end")) {
    replyText = String((const char*)(data["intent_output"]["response"]["speech"]["plain"]["speech"] | ""));
  } else if (!strcmp(et, "tts-end")) {
    ttsUrl = String((const char*)(data["tts_output"]["url"] | ""));
  } else if (!strcmp(et, "error")) {
    runFailed = true;
    lastError = String((const char*)(data["code"] | "")) + ": " + String((const char*)(data["message"] | ""));
    streaming = false;
  } else if (!strcmp(et, "run-end")) {
    runEnded = true; streaming = false;
  }
}

static void wsEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:    authed = false; break;
    case WStype_DISCONNECTED: authed = false; streaming = false; if (voiceState != V_OFF) setState(V_CONNECTING); break;
    case WStype_TEXT:         onText(payload, length); break;
    default: break;
  }
}

static String absoluteUrl(const String& u) {
  if (u.startsWith("http")) return u;
  return "http://" + cfg.haHost + ":" + String(cfg.haPort) + u;
}

static void beginListening() {
  hold(true);
  voiceBeepRequest = true;
  startRun(RUN_STT);
  setState(V_LISTEN);
}

static void handleHeard() {
  String text = heardText; text.trim();
  xSemaphoreTake(dataLock, portMAX_DELAY); voiceHeard = text; voiceReply = ""; xSemaphoreGive(dataLock);
  voiceDirty = true;
  if (text.isEmpty()) { hold(false); setState(V_IDLE); return; }
  String reply;
  if (handleLocalCommand(text, reply)) {
    xSemaphoreTake(dataLock, portMAX_DELAY); voiceReply = reply; xSemaphoreGive(dataLock);
    startRun(RUN_TTS, reply);
  } else {
    startRun(RUN_INTENT, text);                 // lights, questions... handled by Home Assistant
  }
  setState(V_THINK);
}

// ------------------------------------------------------------------ task
void voiceTask(void*) {
  micBegin();
  static int32_t raw[512];
  static uint8_t frame[1 + 512 * 2];
  for (;;) {
    if (restartRequested) {
      restartRequested = false;
      if (wsStarted) { ws.disconnect(); wsStarted = false; }
      authed = false; streaming = false; hold(false); setState(V_OFF);
    }
    bool ready = WiFi.status() == WL_CONNECTED && cfg.haToken.length() > 10 && cfg.haHost.length() > 0;
    if (!ready) {
      if (voiceState != V_OFF) setState(V_OFF);
      if (wsStarted) { ws.disconnect(); wsStarted = false; }
      size_t got; i2s_read(I2S_NUM_0, raw, sizeof(raw), &got, pdMS_TO_TICKS(100));   // keep DMA drained
      continue;
    }
    if (!wsStarted) {
      ws.begin(cfg.haHost.c_str(), cfg.haPort, "/api/websocket");
      ws.onEvent(wsEvent);
      ws.setReconnectInterval(5000);
      wsStarted = true;
      setState(V_CONNECTING);
    }
    ws.loop();

    // microphone: 512 samples = 32 ms; always read so the DMA never overflows
    size_t got = 0;
    i2s_read(I2S_NUM_0, raw, sizeof(raw), &got, pdMS_TO_TICKS(60));
    int n = got / 4;
    if (streaming && handlerId >= 0 && n > 0 && ws.isConnected()) {
      frame[0] = (uint8_t)handlerId;
      for (int i = 0; i < n; i++) {
        int32_t s = raw[i] >> MIC_SHIFT;
        if (s > 32767) s = 32767; else if (s < -32768) s = -32768;
        frame[1 + i * 2] = s & 0xFF;
        frame[2 + i * 2] = (s >> 8) & 0xFF;
      }
      ws.sendBIN(frame, 1 + n * 2);
    }

    if (!authed) continue;
    uint32_t inState = millis() - stateSince;
    switch (voiceState) {
      case V_CONNECTING:
      case V_OFF:
        setState(V_IDLE);
        break;

      case V_IDLE:
        if (talkRequested) { talkRequested = false; beginListening(); }
        else if (cfg.wakeWord && !audioTtsBusy && millis() >= nextWakeAt) { startRun(RUN_WAKE); setState(V_WAKE); }
        break;

      case V_WAKE:
        if (talkRequested) { talkRequested = false; endAudio(); beginListening(); break; }
        if (wakeHeard) { wakeHeard = false; hold(true); voiceBeepRequest = true; setState(V_LISTEN); break; }
        if (!cfg.wakeWord) { endAudio(); setState(V_IDLE); break; }
        if (runEnded || runFailed) {
          // restart; if HA ended it quickly (no wake-word engine installed?) back off for 10 s
          if (millis() - runStarted < 3000) {
            nextWakeAt = millis() + 10000;
            if (lastError.length()) {
              xSemaphoreTake(dataLock, portMAX_DELAY); voiceReply = "Wake word: " + lastError; xSemaphoreGive(dataLock);
              voiceDirty = true;
            }
          }
          setState(V_IDLE);
        }
        break;

      case V_LISTEN:
        if (sttDone) { handleHeard(); break; }
        if (inState > 12000) endAudio();                              // stop sending, wait for stt-end
        if (runFailed || (runEnded && !sttDone) || inState > 20000) { hold(false); setState(V_IDLE); }
        break;

      case V_THINK:
        if (ttsUrl.length()) {
          if (replyText.length()) { xSemaphoreTake(dataLock, portMAX_DELAY); voiceReply = replyText; xSemaphoreGive(dataLock); }
          audioQueueUrl(absoluteUrl(ttsUrl));
          setState(V_SPEAK);
        } else if (runEnded || runFailed || inState > 15000) {
          xSemaphoreTake(dataLock, portMAX_DELAY);
          if (replyText.length()) voiceReply = replyText;
          else if (lastError.length()) voiceReply = lastError;
          xSemaphoreGive(dataLock);
          hold(false); setState(V_IDLE);
        }
        break;

      case V_SPEAK:
        if ((inState > 1500 && !audioTtsBusy) || inState > 30000) { hold(false); setState(V_IDLE); }
        break;
    }
  }
}
