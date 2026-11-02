// Internet data: weather (Open-Meteo), stocks (Finnhub), news (RSS), phone messages (ntfy.sh)
#include "app.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

SemaphoreHandle_t dataLock;
Weather weather;
Quote   quotes[6];
int     quoteCount = 0;
String  headlines[8];
int     headlineCount = 0;
Message lastMsg;
volatile bool dataDirty = true, newMessageFlag = false, refetchAll = false;
static String ntfyLastId = "";

const char* weatherText(int c) {
  if (c == 0) return "Clear";
  if (c <= 2) return "Partly cloudy";
  if (c == 3) return "Cloudy";
  if (c <= 48) return "Fog";
  if (c <= 57) return "Drizzle";
  if (c <= 67) return "Rain";
  if (c <= 77) return "Snow";
  if (c <= 82) return "Showers";
  if (c <= 86) return "Snow showers";
  return "Thunderstorm";
}

static String decodeEntities(String s) {
  s.replace("&amp;", "&");  s.replace("&quot;", "\"");
  s.replace("&#39;", "'");  s.replace("&apos;", "'");
  s.replace("&lt;", "<");   s.replace("&gt;", ">");
  s.replace("&#8217;", "'"); s.replace("&#8216;", "'");
  s.replace("&#8220;", "\""); s.replace("&#8221;", "\"");
  s.replace("\xE2\x80\x99", "'"); s.replace("\xE2\x80\x98", "'");
  s.replace("\xE2\x80\x9C", "\""); s.replace("\xE2\x80\x9D", "\"");
  s.replace("\xE2\x80\x93", "-"); s.replace("\xE2\x80\x94", "-");
  s.trim();
  return s;
}

static bool httpBegin(HTTPClient& http, WiFiClientSecure& client, const String& url) {
  client.setInsecure();                 // public read-only data, no certificate pinning
  http.useHTTP10(true);                 // no chunked encoding -> stream-parse
  http.setTimeout(8000);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  return http.begin(client, url);
}

static void fetchWeather() {
  String url = "https://api.open-meteo.com/v1/forecast?latitude=" + String(cfg.lat, 3) +
               "&longitude=" + String(cfg.lon, 3) +
               "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min"
               "&forecast_days=1&timezone=auto&temperature_unit=" + (cfg.fahrenheit ? "fahrenheit" : "celsius");
  WiFiClientSecure client; HTTPClient http;
  if (!httpBegin(http, client, url)) return;
  if (http.GET() == 200) {
    JsonDocument doc;
    if (!deserializeJson(doc, http.getStream())) {
      Weather w;
      w.ok   = true;
      w.temp = doc["current"]["temperature_2m"] | 0.0f;
      w.code = doc["current"]["weather_code"] | 0;
      w.hi   = doc["daily"]["temperature_2m_max"][0] | 0.0f;
      w.lo   = doc["daily"]["temperature_2m_min"][0] | 0.0f;
      xSemaphoreTake(dataLock, portMAX_DELAY); weather = w; xSemaphoreGive(dataLock);
      dataDirty = true;
    }
  }
  http.end();
}

static void fetchStocks() {
  if (cfg.finnhub.isEmpty()) return;
  Quote local[6]; int n = 0;
  String list = cfg.symbols + ",";
  int start = 0;
  while (n < 6) {
    int comma = list.indexOf(',', start);
    if (comma < 0) break;
    String sym = list.substring(start, comma); sym.trim(); sym.toUpperCase();
    start = comma + 1;
    if (sym.isEmpty()) continue;
    local[n].sym = sym;
    WiFiClientSecure client; HTTPClient http;
    if (httpBegin(http, client, "https://finnhub.io/api/v1/quote?symbol=" + sym + "&token=" + cfg.finnhub)) {
      if (http.GET() == 200) {
        JsonDocument doc;
        if (!deserializeJson(doc, http.getStream())) {
          local[n].price  = doc["c"]  | 0.0f;
          local[n].change = doc["d"]  | 0.0f;
          local[n].pct    = doc["dp"] | 0.0f;
          local[n].ok     = local[n].price > 0;
        }
      }
      http.end();
    }
    n++;
    vTaskDelay(pdMS_TO_TICKS(250));
  }
  xSemaphoreTake(dataLock, portMAX_DELAY);
  for (int i = 0; i < n; i++) quotes[i] = local[i];
  quoteCount = n;
  xSemaphoreGive(dataLock);
  dataDirty = true;
}

static void fetchNews() {
  WiFiClientSecure client; HTTPClient http;
  if (!httpBegin(http, client, cfg.rssUrl)) return;
  if (http.GET() == 200) {
    WiFiClient& s = http.getStream();
    s.setTimeout(4000);
    String local[8]; int n = 0;
    if (s.find("<item>")) {
      while (n < 8 && s.find("<title>")) {
        String t;
        if (s.peek() == '<') { s.find("<![CDATA["); t = s.readStringUntil(']'); }
        else t = s.readStringUntil('<');
        t = decodeEntities(t);
        if (t.length() > 3) local[n++] = t;
      }
    }
    if (n > 0) {
      xSemaphoreTake(dataLock, portMAX_DELAY);
      for (int i = 0; i < n; i++) headlines[i] = local[i];
      headlineCount = n;
      xSemaphoreGive(dataLock);
      dataDirty = true;
    }
  }
  http.end();
}

static void pollNtfy() {
  String since = ntfyLastId.isEmpty() ? "2m" : ntfyLastId;
  WiFiClientSecure client; HTTPClient http;
  if (!httpBegin(http, client, "https://ntfy.sh/" + cfg.ntfyTopic + "/json?poll=1&since=" + since)) return;
  if (http.GET() == 200) {
    WiFiClient& s = http.getStream();
    s.setTimeout(3000);
    while (s.connected() || s.available()) {
      String line = s.readStringUntil('\n');
      if (line.length() < 2) { if (!s.available()) break; else continue; }
      JsonDocument doc;
      if (deserializeJson(doc, line)) continue;
      if (strcmp(doc["event"] | "", "message") != 0) continue;
      Message m;
      m.title  = String((const char*)(doc["title"] | "From phone"));
      m.text   = String((const char*)(doc["message"] | ""));
      m.when   = doc["time"] | (long)time(nullptr);
      m.unread = true;
      ntfyLastId = String((const char*)(doc["id"] | ""));
      xSemaphoreTake(dataLock, portMAX_DELAY); lastMsg = m; xSemaphoreGive(dataLock);
      newMessageFlag = true;
      dataDirty = true;
    }
  }
  http.end();
}

void netTask(void*) {
  uint32_t tWeather = 0, tStocks = 0, tNews = 0, tNtfy = 0;
  bool first = true;
  String lastTopic;
  for (;;) {
    if (WiFi.status() == WL_CONNECTED) {
      uint32_t now = millis();
      if (refetchAll) { first = true; refetchAll = false; }
      if (cfg.ntfyTopic != lastTopic) { lastTopic = cfg.ntfyTopic; ntfyLastId = ""; }
      if (first || now - tNtfy    > 15UL * 1000)      { pollNtfy();     tNtfy = now; }
      if (first || now - tWeather > 15UL * 60 * 1000) { fetchWeather(); tWeather = now; }
      if (first || now - tStocks  > 2UL * 60 * 1000)  { fetchStocks();  tStocks = now; }
      if (first || now - tNews    > 15UL * 60 * 1000) { fetchNews();    tNews = now; }
      first = false;
    }
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}
