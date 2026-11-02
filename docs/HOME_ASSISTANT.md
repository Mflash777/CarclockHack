# Setting up voice control (Home Assistant)

HackClock's voice works like an Alexa. The **listening** and **understanding** happen on your own
**Home Assistant** server, at home, with no cloud account required:

```
you speak --> clock mic --> Home Assistant:  wake word (openWakeWord)
                                              speech -> text (Whisper)
          <-- speaker   <-- text -> speech (Piper)  <-- answer (clock or HA)
```

The clock answers alarms, timers, time, weather, stocks, news, messages and music controls **by
itself**. Everything else goes to Home Assistant's assistant: turning on lights, asking questions,
and anything else you've connected to HA.

## 1. Get Home Assistant running (once)

Pick one:
- **Raspberry Pi 4 or 5** (4 GB+): flash *Home Assistant OS* with Raspberry Pi Imager (the
  "Other specific-purpose OS > Home automation" category).
- **Home Assistant Green**: plug-and-play box.
- **An old laptop/PC**: install Home Assistant OS, or run it in a VM.

Open `http://homeassistant.local:8123` and create your account.

> Whisper runs much faster on a Pi 5 or a PC than on a Pi 4. On a Pi 4, choose the `tiny-int8`
> model. *Home Assistant Cloud* (paid) can do the speech parts instead if your server is slow.

## 2. Install the three voice add-ons

**Settings > Add-ons > Add-on store**, then install and **Start** each one (turn on "Start on boot"):

| Add-on | Job |
|---|---|
| **openWakeWord** | listens for the wake word |
| **Whisper** | speech -> text |
| **Piper** | text -> speech (pick a voice you like) |

Then go to **Settings > Devices & services**. All three show up as discovered **Wyoming Protocol**
devices; click **Configure** on each one.

## 3. Make a voice assistant pipeline

**Settings > Voice assistants > Add assistant**:
- Conversation agent: *Home Assistant*, or an AI agent if you've added one (OpenAI / Google / Anthropic integrations)
- Speech-to-text: **faster-whisper**
- Text-to-speech: **piper**
- Wake word: **openWakeWord**, choose a word: `ok nabu`, `hey jarvis`, `hey mycroft`, or `alexa`

Click the star to make it the **preferred** assistant. The clock always uses the preferred one.

## 4. Create a token for the clock

Click your **user name** (bottom left) > **Security** tab > **Long-lived access tokens** > **Create
token**. Name it `HackClock` and copy it (it's shown only once).

## 5. Tell the clock

Open `http://hackclock.local` and fill in the **Voice assistant** section:
- Home Assistant host: `homeassistant.local`, or better, its IP like `192.168.1.50`
- Port: `8123`
- Token: paste it, then press **Save**

The mic dot at the top right of the TFT turns **yellow** when the clock is listening for the wake word.

## Things to say

| Say | What happens |
|---|---|
| "*wake word*, wake me up at 6:45" | one-time alarm (alarm slot 2) |
| "set a timer for 10 minutes" / "how much time is left" / "cancel the timer" | kitchen timer with a countdown on the screen |
| "snooze" / "stop" (while the alarm rings) | snooze 9 min / dismiss |
| "what's the weather" / "do I need an umbrella" | from Open-Meteo |
| "how are my stocks" / "how is Apple doing" | your Finnhub symbols |
| "read the news" | top 3 headlines |
| "read my messages" | last ntfy message |
| "pause" / "play" / "next song" / "volume 7" / "what song is this" | Bluetooth music |
| "what time is it" / "what's the date" | clock |
| "turn on the bedroom light" | Home Assistant (if you have smart devices) |
| anything else | your HA conversation agent |

No wake word? Press **TALK** (or hold TALK to switch wake-word listening on/off).

## Troubleshooting

- **"Home Assistant rejected the token"**: create a new token and paste it again.
- **The mic dot stays grey**: check the host/IP. `homeassistant.local` doesn't resolve on every network, so use the IP.
- **"Wake word: ..." error on screen**: the openWakeWord add-on isn't running, or isn't selected in the preferred pipeline. TALK still works.
- **It hears nothing**: in `firmware/clock/src/pins.h`, change `MIC_CHANNEL_FMT` to `I2S_CHANNEL_FMT_ONLY_RIGHT`,
  or wire the mic's L/R pin to 3V3 instead of GND.
- **Too quiet / too noisy**: change `MIC_SHIFT` (13 = louder, 15 = quieter).
- **The wake word doesn't trigger while music plays loudly**: that's normal without echo cancellation. Press TALK; it pauses the music.
