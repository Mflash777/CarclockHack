// Voice commands the clock answers by itself (no smart-home server logic needed).
// Anything not matched here goes to Home Assistant's conversation agent.
#include "app.h"

QueueHandle_t actionQueue;

static void act(ActType t, int a = 0, int b = 0) {
  Action x; x.type = t; x.a = a; x.b = b;
  xQueueSend(actionQueue, &x, 0);
}

// ---------------------------------------------------------------- text helpers
static String normalise(String s) {
  s.toLowerCase();
  s.replace("a.m.", " am "); s.replace("p.m.", " pm ");
  s.replace("o'clock", " "); s.replace("'", "");
  for (unsigned i = 0; i < s.length(); i++) {
    char c = s[i];
    if (!isalnum((unsigned char)c) && c != ':') s.setCharAt(i, ' ');
  }
  s.replace(":", " : ");
  // number words -> digits
  const char* words[] = {"zero","one","two","three","four","five","six","seven","eight","nine","ten","eleven","twelve",
                         "thirteen","fourteen","fifteen","sixteen","seventeen","eighteen","nineteen","twenty"};
  s = " " + s + " ";
  s.replace(" half an hour ", " 30 minutes "); s.replace(" an hour ", " 1 hour ");
  s.replace(" a minute ", " 1 minute ");       s.replace(" a timer ", " timer ");
  for (int i = 20; i >= 0; i--) s.replace(" " + String(words[i]) + " ", " " + String(i) + " ");
  s.replace(" thirty ", " 30 "); s.replace(" forty ", " 40 "); s.replace(" fifty ", " 50 ");
  s.replace(" a m ", " am "); s.replace(" p m ", " pm ");
  while (s.indexOf("  ") >= 0) s.replace("  ", " ");
  return s;
}

static int tokenize(const String& s, String* tok, int maxTok) {
  int n = 0, i = 0;
  while (i < (int)s.length() && n < maxTok) {
    while (i < (int)s.length() && s[i] == ' ') i++;
    int j = i;
    while (j < (int)s.length() && s[j] != ' ') j++;
    if (j > i) tok[n++] = s.substring(i, j);
    i = j;
  }
  // merge "20 5" -> "25"
  for (int k = 0; k + 1 < n; k++) {
    if (tok[k].length() && isdigit(tok[k][0]) && isdigit(tok[k + 1][0])) {
      int a = tok[k].toInt(), b = tok[k + 1].toInt();
      if (a >= 20 && a % 10 == 0 && a <= 50 && b > 0 && b < 10) {
        tok[k] = String(a + b);
        for (int m = k + 1; m + 1 < n; m++) tok[m] = tok[m + 1];
        n--;
      }
    }
  }
  return n;
}

static bool isNum(const String& t) { return t.length() && isdigit(t[0]); }
static bool has(const String& s, const char* w) { return s.indexOf(w) >= 0; }

// "7 30 am", "7 : 30", "730", "19 45", "7 pm"
static bool parseClockTime(String* tok, int n, int& h, int& m) {
  for (int i = 0; i < n; i++) {
    if (!isNum(tok[i])) continue;
    int v = tok[i].toInt();
    h = v; m = 0;
    int next = i + 1;
    if (v >= 100) { h = v / 100; m = v % 100; }
    else if (next < n && tok[next] == ":" && next + 1 < n && isNum(tok[next + 1])) { m = tok[next + 1].toInt(); next += 2; }
    else if (next < n && isNum(tok[next]) && tok[next].toInt() < 60) { m = tok[next].toInt(); next++; }
    bool pm = false, am = false;
    for (int k = next; k < min(n, next + 3); k++) {
      if (tok[k] == "pm" || tok[k] == "evening" || tok[k] == "tonight" || tok[k] == "night") pm = true;
      if (tok[k] == "am" || tok[k] == "morning") am = true;
    }
    if (h > 23 || m > 59) return false;
    if (pm && h < 12) h += 12;
    if (am && h == 12) h = 0;
    if (!am && !pm && h <= 12) {                       // guess the next occurrence
      time_t now = time(nullptr); struct tm t; localtime_r(&now, &t);
      int nowMin = t.tm_hour * 60 + t.tm_min;
      int amMin = (h % 12) * 60 + m, pmMin = amMin + 720;
      h = (amMin <= nowMin && pmMin > nowMin) ? (h % 12) + 12 : h % 12;
    }
    return true;
  }
  return false;
}

static int parseDurationSeconds(String* tok, int n) {
  int total = 0;
  for (int i = 0; i + 1 < n; i++) {
    if (!isNum(tok[i])) continue;
    int v = tok[i].toInt();
    const String& u = tok[i + 1];
    if (u.startsWith("hour")) total += v * 3600;
    else if (u.startsWith("min")) total += v * 60;
    else if (u.startsWith("sec")) total += v;
  }
  return total;
}

static String durationText(int s) {
  int h = s / 3600, m = (s % 3600) / 60, sec = s % 60;
  String r;
  if (h) r += String(h) + (h == 1 ? " hour " : " hours ");
  if (m) r += String(m) + (m == 1 ? " minute " : " minutes ");
  if (sec && !h) r += String(sec) + (sec == 1 ? " second" : " seconds");
  r.trim();
  return r;
}

static String stockName(const String& sym) {
  const char* map[][2] = {{"AAPL","Apple"},{"MSFT","Microsoft"},{"NVDA","Nvidia"},{"TSLA","Tesla"},{"AMZN","Amazon"},
                          {"GOOGL","Google"},{"GOOG","Google"},{"META","Meta"},{"SPY","the S and P 500"},{"NFLX","Netflix"},
                          {"AMD","A M D"},{"QQQ","the Nasdaq 100"},{"DIS","Disney"},{"NKE","Nike"}};
  for (auto& e : map) if (sym == e[0]) return e[1];
  String spelled;
  for (unsigned i = 0; i < sym.length(); i++) { spelled += sym[i]; spelled += ' '; }
  spelled.trim();
  return spelled;
}

// ---------------------------------------------------------------- the parser
bool handleLocalCommand(const String& raw, String& reply) {
  String s = normalise(raw);
  String tok[40];
  int n = tokenize(s, tok, 40);

  // ---- ringing alarm / timer
  if (ringing && (has(s, " snooze ") || has(s, " 5 more minutes "))) { act(A_SNOOZE); reply = "Okay, snoozing for 9 minutes."; return true; }
  if (ringing && (has(s, " stop ") || has(s, " off ") || has(s, " dismiss ") || has(s, " im up "))) { act(A_DISMISS); reply = "Good morning!"; return true; }

  // ---- timers
  if (has(s, " timer ")) {
    if (has(s, " cancel ") || has(s, " stop ") || has(s, " delete ")) {
      act(A_TIMER_CANCEL); reply = timerEnd ? "Timer cancelled." : "There's no timer running."; return true;
    }
    if (has(s, " how much ") || has(s, " left ") || has(s, " remaining ")) {
      long left = timerEnd ? (long)(timerEnd - time(nullptr)) : 0;
      reply = left > 0 ? durationText(left) + " left on your timer." : "There's no timer running."; return true;
    }
    int secs = parseDurationSeconds(tok, n);
    if (secs > 0) { act(A_TIMER, secs); reply = "Timer set for " + durationText(secs) + "."; return true; }
    reply = "For how long? Say something like, set a timer for 5 minutes."; return true;
  }

  // ---- alarms
  if (has(s, " alarm ") || has(s, " wake me ")) {
    if (has(s, " cancel ") || has(s, " turn off ") || has(s, " delete ") || has(s, " remove ") || has(s, " disable ")) {
      act(A_ALARM_OFF); reply = "Okay, your alarms are off."; return true;
    }
    if (has(s, " what ") || has(s, " when ") || has(s, " is my ") || has(s, " do i have ")) {
      String r;
      for (auto& a : cfg.alarm) if (a.on) r += (r.length() ? " and " : "") + fmtTimeSpoken(a.hour, a.minute);
      reply = r.length() ? "Your alarm is set for " + r + "." : "You don't have any alarms set."; return true;
    }
    int h, m;
    if (parseClockTime(tok, n, h, m)) { act(A_SET_ALARM, h, m); reply = "Okay, alarm set for " + fmtTimeSpoken(h, m) + "."; return true; }
    reply = "What time? Say something like, wake me up at 7 30 AM."; return true;
  }

  // ---- music (Bluetooth)
  bool musicWord = has(s, " music ") || has(s, " song ") || has(s, " track ") || has(s, " spotify ");
  if (has(s, " volume ") || has(s, " louder ") || has(s, " quieter ") || has(s, " turn it up ") || has(s, " turn it down ")) {
    int v = cfg.volume;
    bool setAbs = false;
    for (int i = 0; i < n; i++) if (isNum(tok[i])) { v = constrain(tok[i].toInt(), 0, 10); setAbs = true; break; }
    if (!setAbs) {
      if (has(s, " up ") || has(s, " louder ")) v = min(10, v + 2);
      else if (has(s, " down ") || has(s, " quieter ") || has(s, " lower ")) v = max(0, v - 2);
    }
    act(A_VOLUME, v); reply = "Volume " + String(v) + "."; return true;
  }
  if (has(s, " pause ") || (has(s, " stop ") && musicWord)) { act(A_PAUSE); reply = "Paused."; return true; }
  if ((has(s, " next ") || has(s, " skip ")) && (musicWord || n <= 3)) { act(A_NEXT); reply = "Skipping."; return true; }
  if ((has(s, " previous ") || has(s, " go back ") || has(s, " last song ")) && (musicWord || n <= 4)) { act(A_PREV); reply = "Going back."; return true; }
  if ((has(s, " resume ") || has(s, " play ") || has(s, " unpause ")) && (musicWord || n <= 2 || has(s, " resume "))) {
    if (!audio.btConnected) { reply = "No phone is connected. Pair your phone with HackClock in Bluetooth settings."; return true; }
    act(A_PLAY); reply = "Playing."; return true;
  }
  if (has(s, " what song ") || has(s, " whats playing ") || has(s, " what is playing ") || has(s, " who sings ")) {
    if (!audio.btConnected || audio.title.isEmpty()) { reply = "Nothing is playing right now."; return true; }
    reply = "This is " + audio.title + (audio.artist.length() ? " by " + audio.artist : String("")) + "."; return true;
  }

  // ---- time / date
  if (has(s, " what time ") || has(s, " the time ") || s == " time ") {
    time_t now = time(nullptr); struct tm t; localtime_r(&now, &t);
    reply = "It's " + fmtTimeSpoken(t.tm_hour, t.tm_min) + "."; return true;
  }
  if (has(s, " what day ") || has(s, " date ") || has(s, " what is today ")) {
    time_t now = time(nullptr); struct tm t; localtime_r(&now, &t);
    char b[48]; strftime(b, sizeof(b), "%A, %B %d", &t);
    reply = "Today is " + String(b) + "."; return true;
  }

  // ---- weather
  if (has(s, " weather ") || has(s, " temperature ") || has(s, " outside ") || has(s, " rain ") || has(s, " umbrella ") || has(s, " cold ") || has(s, " hot ")) {
    Weather w; xSemaphoreTake(dataLock, portMAX_DELAY); w = weather; xSemaphoreGive(dataLock);
    if (!w.ok) { reply = "I don't have the weather yet."; return true; }
    reply = "Right now it's " + String((int)round(w.temp)) + " degrees and " + String(weatherText(w.code)) +
            ". Today's high is " + String((int)round(w.hi)) + " and the low is " + String((int)round(w.lo)) + ".";
    String low = String(weatherText(w.code)); low.toLowerCase();
    if (has(s, " umbrella ") || has(s, " rain ")) reply += (low.indexOf("rain") >= 0 || low.indexOf("shower") >= 0 || low.indexOf("drizzle") >= 0 || low.indexOf("thunder") >= 0)
                                                         ? " You'll want an umbrella." : " No rain right now.";
    return true;
  }

  // ---- stocks
  if (has(s, " stock") || has(s, " market ") || has(s, " shares ") || has(s, " portfolio ")) {
    Quote q[6]; int cnt;
    xSemaphoreTake(dataLock, portMAX_DELAY); cnt = quoteCount; for (int i = 0; i < cnt; i++) q[i] = quotes[i]; xSemaphoreGive(dataLock);
    if (!cnt) { reply = cfg.finnhub.isEmpty() ? "Add a Finnhub key on the settings page first." : "I don't have stock prices yet."; return true; }
    String r;
    for (int i = 0; i < cnt; i++) {
      String name = stockName(q[i].sym), lname = name; lname.toLowerCase();
      String lsym = q[i].sym; lsym.toLowerCase();
      bool asked = has(s, (" " + lname).c_str()) || has(s, (" " + lsym + " ").c_str());
      if (!q[i].ok) continue;
      String line = name + " is at " + String((int)round(q[i].price)) + " dollars, " + (q[i].pct >= 0 ? "up " : "down ") +
                    String(fabs(q[i].pct), 1) + " percent. ";
      if (asked) { reply = line; return true; }
      if (i < 3) r += line;
    }
    reply = r.length() ? r : "Quotes aren't available right now."; return true;
  }

  // ---- news / messages
  if (has(s, " news ") || has(s, " headlines ")) {
    String r = "Here are the headlines. ";
    xSemaphoreTake(dataLock, portMAX_DELAY);
    int cnt = min(headlineCount, 3);
    for (int i = 0; i < cnt; i++) r += headlines[i] + ". ";
    xSemaphoreGive(dataLock);
    reply = cnt ? r : "I don't have any headlines yet."; act(A_PAGE, 3); return true;
  }
  if (has(s, " message")) {
    Message m; xSemaphoreTake(dataLock, portMAX_DELAY); m = lastMsg; xSemaphoreGive(dataLock);
    reply = m.text.length() ? "Your last message says: " + m.text : "You don't have any messages."; act(A_PAGE, 4); return true;
  }

  // ---- display
  if (has(s, " night mode ") || has(s, " dim the ") || has(s, " screen off ")) { act(A_NIGHT); reply = "Okay."; return true; }

  return false;
}
