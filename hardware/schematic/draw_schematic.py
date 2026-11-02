#!/usr/bin/env python3
"""Draws the HackClock v2 schematic (net-label style), 2 sheets -> schematic.pdf + PNGs."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Polygon, FancyBboxPatch
from matplotlib.backends.backend_pdf import PdfPages

INK, NET, PWR, GND_C, BOX = "#1d1d1f", "#0b6bcb", "#c0392b", "#2d7d46", "#f6f4ee"
ax = None

def new_sheet(title, sheet):
    global ax
    fig, a = plt.subplots(figsize=(16.5, 11.7)); ax = a
    ax.set_xlim(0, 420); ax.set_ylim(0, 297); ax.set_aspect("equal"); ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.add_patch(Rectangle((4, 4), 412, 289, fill=False, ec=INK, lw=1.2))
    ax.add_patch(Rectangle((300, 4), 116, 22, fill=False, ec=INK, lw=1.2))
    ax.text(304, 18, "HackClock GT - " + title, fontsize=10, fontweight="bold")
    ax.text(304, 11.5, f"Hack Club Half Life  |  rev 3.2  |  sheet {sheet}/2", fontsize=7.5)
    ax.text(304, 6.5, "Same names = same net (net-label schematic)", fontsize=6.5, color="#555")
    return fig

def line(pts, c=INK, lw=1.4):
    xs, ys = zip(*pts); ax.plot(xs, ys, color=c, lw=lw, solid_capstyle="round")
def dot(x, y): ax.add_patch(Circle((x, y), 0.9, color=INK, zorder=5))
def label(x, y, text, side="right", color=NET):
    w = 2.1 * len(text) + 4
    if side == "right":
        pts = [(x, y), (x + 2.5, y + 2.4), (x + w, y + 2.4), (x + w, y - 2.4), (x + 2.5, y - 2.4)]; tx, ha = x + 3.2, "left"
    else:
        pts = [(x, y), (x - 2.5, y + 2.4), (x - w, y + 2.4), (x - w, y - 2.4), (x - 2.5, y - 2.4)]; tx, ha = x - 3.2, "right"
    ax.add_patch(Polygon(pts, closed=True, fc="white", ec=color, lw=1.1, zorder=4))
    ax.text(tx, y, text, color=color, fontsize=7, va="center", ha=ha, family="monospace", zorder=6)
def netcolor(n): return PWR if n.startswith("+") else GND_C if n == "GND" else NET
def vcc(x, y, text):
    line([(x, y), (x, y + 4)], PWR); line([(x - 3, y + 4), (x + 3, y + 4)], PWR, 1.8)
    ax.text(x, y + 6, text, color=PWR, fontsize=7.5, ha="center", fontweight="bold")
def gnd(x, y):
    line([(x, y), (x, y - 3)], GND_C)
    for i, w in enumerate([3.2, 2.1, 1.0]): line([(x - w, y - 3 - i * 1.2), (x + w, y - 3 - i * 1.2)], GND_C, 1.5)
def resistor_v(x, y1, y2, name, val):
    mid = (y1 + y2) / 2
    line([(x, y1), (x, mid + 5)]); line([(x, mid - 5), (x, y2)])
    ax.add_patch(Rectangle((x - 1.8, mid - 5), 3.6, 10, fill=False, ec=INK, lw=1.4))
    ax.text(x + 3.2, mid + 1.5, name, fontsize=7.5, fontweight="bold"); ax.text(x + 3.2, mid - 3, val, fontsize=7)
def resistor_h(x1, x2, y, name, val):
    mid = (x1 + x2) / 2
    line([(x1, y), (mid - 5, y)]); line([(mid + 5, y), (x2, y)])
    ax.add_patch(Rectangle((mid - 5, y - 1.8), 10, 3.6, fill=False, ec=INK, lw=1.4))
    ax.text(mid, y + 3.2, f"{name} {val}", fontsize=7, ha="center")
def cap_v(x, y1, y2, name, val, polar=False):
    mid = (y1 + y2) / 2
    line([(x, y1), (x, mid + 1)]); line([(x, mid - 1), (x, y2)])
    line([(x - 3, mid + 1), (x + 3, mid + 1)], INK, 2); line([(x - 3, mid - 1), (x + 3, mid - 1)], INK, 2)
    if polar: ax.text(x - 5, mid + 2, "+", fontsize=8)
    ax.text(x + 4, mid + 1, name, fontsize=7.5, fontweight="bold"); ax.text(x + 4, mid - 3.5, val, fontsize=7)
def box(x, y, w, h, title, sub=""):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.5", fc=BOX, ec=INK, lw=1.5))
    ax.text(x + w / 2, y + h + 2.5, title, ha="center", fontsize=8.5, fontweight="bold")
    if sub: ax.text(x + w / 2, y - 4, sub, ha="center", fontsize=6.6, color="#555")
def pins(x, y_top, names, nets, side, pitch=6, lab=True):
    for i, (n, net) in enumerate(zip(names, nets)):
        y = y_top - i * pitch
        if side == "left":
            line([(x, y), (x - 8, y)]); ax.text(x + 1.5, y, n, fontsize=6.8, va="center")
            ax.text(x - 4, y + 1.2, str(i + 1), fontsize=5.5, ha="center", color="#777")
            if net and lab: label(x - 8, y, net, "left", netcolor(net))
        else:
            line([(x, y), (x + 8, y)]); ax.text(x - 1.5, y, n, fontsize=6.8, va="center", ha="right")
            ax.text(x + 4, y + 1.2, str(i + 1), fontsize=5.5, ha="center", color="#777")
            if net and lab: label(x + 8, y, net, "right", netcolor(net))
def diode_h(x1, x2, y, name, val):
    mid = (x1 + x2) / 2
    line([(x1, y), (mid - 3, y)]); line([(mid + 3, y), (x2, y)])
    ax.add_patch(Polygon([(mid - 3, y + 3), (mid - 3, y - 3), (mid + 3, y)], closed=True, fill=False, ec=INK, lw=1.3))
    line([(mid + 3, y + 3), (mid + 3, y - 3)], INK, 2)
    ax.text(mid, y + 5, f"{name} {val}", fontsize=7, ha="center")

# =========================================================== SHEET 1: clock PCB
fig1 = new_sheet("clock carrier PCB", 1)

box(22, 228, 46, 52, "J1  TFT 2.0\" ST7789 240x320", "SPI, 3.3 V")
pins(68, 274, ["GND", "VCC", "SCL", "SDA", "RES", "DC", "CS", "BLK"],
     ["GND", "+3V3", "TFT_SCK", "TFT_MOSI", "TFT_RST", "TFT_DC", "TFT_CS", "TFT_BL"], "right")
box(118, 250, 40, 26, "J2  HT16K33 7-segment", "4-digit 0.56\", I2C 0x70")
pins(158, 270, ["GND", "VCC", "SDA", "SCL"], ["GND", "+3V3", "SDA", "SCL"], "right")
box(212, 250, 40, 26, "J3  DS3231 RTC", "I2C 0x68, CR2032 backup")
pins(252, 270, ["GND", "VCC", "SDA", "SCL"], ["GND", "+3V3", "SDA", "SCL"], "right")
box(306, 238, 40, 38, "J6  INMP441 microphone", "I2S, 16 kHz, L/R = GND")
pins(346, 270, ["VDD", "GND", "L/R", "WS", "SCK", "SD"], ["+3V3", "GND", "GND", "MIC_WS", "MIC_SCK", "MIC_SD"], "right")

box(150, 160, 52, 50, "U1  Seeed XIAO ESP32-S3", "")
pins(150, 204, ["D0/GPIO1", "D1/GPIO2", "D2/GPIO3", "D3/GPIO4", "D4/GPIO5", "D5/GPIO6", "D6/GPIO43"],
     ["BTN", "TFT_DC", "TFT_CS", "BUZ", "SDA", "SCL", "MIC_SCK"], "left", pitch=7)
pins(202, 204, ["5V", "GND", "3V3", "D10/GPIO9", "D9/GPIO8", "D8/GPIO7", "D7/GPIO44"],
     ["+5V", "GND", "+3V3", "TFT_MOSI", "MIC_SD", "TFT_SCK", "MIC_WS"], "right", pitch=7)

box(306, 178, 40, 32, "J7  AUDIO link", "to audio board (sheet 2)")
pins(346, 204, ["5V", "GND", "SDA", "SCL", "BL"], ["+5V", "GND", "SDA", "SCL", "TFT_BL"], "right")

# power in + bulk caps
ax.text(262, 158, "Power in + bulk capacitors", fontsize=8, fontweight="bold")
box(262, 130, 18, 16, "J8 5V IN", "USB-C breakout (tail)")
line([(280, 142), (288, 142)]); line([(280, 134), (288, 134)]); gnd(288, 134)
ax.text(278.5, 142, "5V", fontsize=6.5, ha="right", va="center"); ax.text(278.5, 134, "GND", fontsize=6.5, ha="right", va="center")
diode_h(288, 308, 142, "D2", "1N5819"); line([(308, 142), (308, 146)]); vcc(308, 146, "+5V")
ax.text(298, 133, "(+5V_IN)", fontsize=6, color="#555", ha="center")
for (x, nm, val, pol, rail) in [(330, "C5", "470uF", True, "+5V"), (352, "C4", "10uF", False, "+5V"), (374, "C3", "10uF", False, "+3V3")]:
    vcc(x, 144, rail); cap_v(x, 144, 128, nm, val, pol); gnd(x, 128)

# TFT reset
ax.text(22, 205, "TFT power-on reset", fontsize=8, fontweight="bold")
vcc(40, 192, "+3V3"); resistor_v(40, 192, 172, "R7", "10k")
line([(40, 172), (40, 166)]); dot(40, 172); line([(40, 172), (55, 172)]); label(55, 172, "TFT_RST", "right")
cap_v(40, 166, 152, "C2", "1uF"); gnd(40, 152)

# buzzer driver
ax.text(22, 132, "Backup buzzers (2 passive, parallel) via J5", fontsize=8, fontweight="bold")
line([(30, 92), (40, 92)]); label(30, 92, "BUZ", "left")
resistor_h(40, 62, 92, "R1", "1k"); line([(62, 92), (72, 92)]); dot(66, 92)
resistor_v(66, 92, 70, "R2", "10k"); gnd(66, 70)
ax.add_patch(Circle((80, 92), 8, fill=False, ec=INK, lw=1.3))
line([(72, 92), (77, 92)]); line([(77, 97), (77, 87)], INK, 2.2)
line([(77, 95), (84, 101)]); line([(77, 89), (84, 83)])
ax.add_patch(Polygon([(84, 83), (80.6, 84.2), (82.4, 86.6)], closed=True, color=INK))
ax.text(90, 93, "Q1\n2N3904", fontsize=7.5)
line([(84, 83), (84, 76)]); gnd(84, 76)
line([(84, 101), (84, 108)]); dot(84, 108); line([(84, 108), (130, 108)])
for i, bx in enumerate([110, 130]):
    line([(bx, 108), (bx, 112)]); ax.add_patch(Rectangle((bx - 4, 112), 8, 7, fill=False, ec=INK, lw=1.4))
    ax.add_patch(Polygon([(bx - 4, 119), (bx + 4, 119), (bx + 6, 123), (bx - 6, 123)], closed=True, fill=False, ec=INK))
    ax.text(bx, 115.5, f"BZ{i+1}", fontsize=5.5, ha="center", va="center"); line([(bx, 123), (bx, 126)])
line([(96, 126), (130, 126)]); dot(110, 108); dot(110, 126)
line([(120, 126), (120, 128)]); vcc(120, 128, "+5V")
line([(96, 108), (96, 113)]); dot(96, 108)
ax.add_patch(Polygon([(93, 113), (99, 113), (96, 118)], closed=True, fill=False, ec=INK, lw=1.3))
line([(93, 118), (99, 118)], INK, 2); line([(96, 118), (96, 126)]); dot(96, 126)
ax.text(91, 115, "D1\n1N4148", fontsize=6.5, ha="right")

# button ladder
ax.text(176, 140, "Buttons: resistor ladder on one ADC pin (J4)", fontsize=8, fontweight="bold")
vcc(186, 126, "+3V3"); resistor_v(186, 126, 108, "R3", "10k")
line([(186, 108), (186, 100)]); dot(186, 100)
line([(166, 100), (330, 100)]); label(166, 100, "BTN", "left")
cap_v(176, 100, 86, "C1", "100nF"); gnd(176, 86); dot(176, 100)
def button(x, y_top, y_bot, name):
    line([(x, y_top), (x, y_top - 3)])
    ax.add_patch(Circle((x, y_top - 3.6), 0.7, fill=False, ec=INK)); ax.add_patch(Circle((x, y_top - 9.4), 0.7, fill=False, ec=INK))
    line([(x + 1.5, y_top - 3.2), (x + 4.5, y_top - 9.6)]); line([(x + 3, y_top - 6.4), (x + 6, y_top - 6.4)])
    line([(x, y_top - 10), (x, y_bot)]); gnd(x, y_bot)
    ax.text(x - 2, y_top - 6.5, name, fontsize=6.8, ha="right", fontweight="bold")
dot(204, 100); button(204, 100, 74, "SNOOZE = spoiler")
for (x, r, val, nm) in [(232, "R4", "2k2", "MODE"), (260, "R5", "4k7", "UP (not fitted)"), (288, "R6", "10k", "DOWN (not fitted)"), (316, "R8", "15k", "TALK")]:
    if x != 316: dot(x, 100)
    resistor_v(x, 100, 84, r, val); button(x, 84, 58, nm)
ax.text(176, 46, "Released 3.3 V | SNOOZE (spoiler) 0 V | MODE 0.6 V | TALK 1.98 V   (UP / DOWN: leave the buttons off)", fontsize=6.8, color="#555")
ax.text(176, 40, "J4: GND, SNZ (spoiler switch), MODE_N, UP_N, DOWN_N (unused), TALK_N - each switch wires between its pin and GND", fontsize=6.3, color="#555")

notes = ["NOTES",
         "1. All modules run at 3.3 V; only the buzzers, amp and audio board use 5 V.",
         "2. I2C bus (SDA/SCL) is shared: RTC 0x68, 7-segment 0x70, audio board 0x42.",
         "    Pull-ups are on the RTC / 7-seg modules (to 3.3 V).",
         "3. DS3231 'ZS-042': use a CR2032 and remove the charging diode/resistor.",
         "4. TFT pin order differs between sellers: wire by NAME.",
         "5. TFT BLK is dimmed by the audio board (PWM on its GPIO4).",
         "6. Power: 5 V 2-3 A USB-C into J8 (tail). The XIAO's own USB is for programming."]
for i, n in enumerate(notes):
    ax.text(12, 58 - i * 6, n, fontsize=6.5 if i else 8, fontweight="bold" if i == 0 else "normal")

# =========================================================== SHEET 2: audio board + system
fig2 = new_sheet("audio, power + system", 2)
# system block diagram
ax.text(20, 280, "System overview", fontsize=10, fontweight="bold")
blocks = [(20, 236, 70, 28, "Phone", "Bluetooth music"),
          (120, 236, 80, 28, "Audio board\nESP32 WROVER", "BT speaker, TTS player"),
          (230, 236, 80, 28, "Clock board\nXIAO ESP32-S3", "displays, mic, buttons"),
          (330, 236, 75, 28, "Home Assistant", "wake word, Whisper STT,\nPiper TTS, smart home")]
for (x, y, w, h, t, s) in blocks:
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=3", fc="#fff4e5", ec="#d9822b", lw=1.6))
    ax.text(x + w / 2, y + h - 9, t, ha="center", va="center", fontsize=8.5, fontweight="bold")
    ax.text(x + w / 2, y + 6, s, ha="center", va="center", fontsize=6.3, color="#555")
def arrow(x1, y1, x2, y2, t, dy=3):
    ax.annotate("", (x2, y2), (x1, y1), arrowprops=dict(arrowstyle="<->", color="#555", lw=1.2))
    ax.text((x1 + x2) / 2, (y1 + y2) / 2 + dy, t, ha="center", fontsize=6.5, color="#555")
arrow(90, 250, 120, 250, "Bluetooth")
arrow(200, 250, 230, 250, "I2C (0x42)")
arrow(310, 250, 330, 250, "WiFi")
ax.annotate("", (160, 236), (365, 222), arrowprops=dict(arrowstyle="->", color="#555", lw=1, connectionstyle="arc3,rad=-0.15"))
ax.text(262, 206, "audio board downloads the spoken reply (MP3) from HA over WiFi", fontsize=6.5, color="#555", ha="center")

# audio board pins
box(150, 112, 56, 70, "Audio board: ESP32-DevKitC-VE (WROVER-E)", "any classic ESP32 with PSRAM - NOT an S3/C3 (no Bluetooth Classic)")
left_names = ["5V / VIN", "GND", "GPIO21 (SDA)", "GPIO22 (SCL)", "GPIO4"]
left_nets = ["+5V", "GND", "SDA", "SCL", "TFT_BL"]
pins(150, 172, left_names, left_nets, "left", pitch=8)
ax.text(100, 182, "to clock PCB J7 \"AUDIO\"", fontsize=7, color="#555", ha="center")
right_names = ["GPIO26", "GPIO25", "GPIO27", "5V / VIN", "GND"]
right_nets = ["I2S_BCLK", "I2S_LRC", "I2S_DIN", "+5V", "GND"]
pins(206, 172, right_names, right_nets, "right", pitch=8)

box(282, 112, 44, 60, "MAX98357A I2S amplifier", "3 W class-D, mono")
pins(282, 164, ["BCLK", "LRC", "DIN", "VIN", "GND", "GAIN", "SD"], ["I2S_BCLK", "I2S_LRC", "I2S_DIN", "+5V", "GND", "", ""], "left", pitch=7)
ax.text(304, 102, "GAIN, SD: leave open (9 dB gain, L+R mix)", fontsize=6.3, color="#555", ha="center")
# speaker
line([(326, 152), (350, 152)]); line([(326, 136), (350, 136)])
ax.text(328, 154, "OUT+", fontsize=6.5); ax.text(328, 138, "OUT-", fontsize=6.5)
ax.add_patch(Rectangle((350, 134), 7, 20, fill=False, ec=INK, lw=1.5))
ax.add_patch(Polygon([(357, 134), (357, 154), (370, 164), (370, 124)], closed=True, fill=False, ec=INK, lw=1.5))
ax.text(362, 116, "SPK1  2\" 4 ohm 3-5 W", fontsize=7.5, ha="center", fontweight="bold")
# direct wires drawn between board and amp
for y_b, y_a in [(172, 164), (164, 157), (156, 150)]:
    pass

ax.text(20, 96, "Audio board notes", fontsize=8.5, fontweight="bold")
an = ["- I2S_* nets are short Dupont wires from the ESP32 board straight to the amp (not on the PCB).",
      "- Speaker wires: solder to the amp's screw terminal / pads; keep them twisted.",
      "- Both boards run from the 5 V USB-C input (J8). The amp draws ~0.8 A at full volume.",
      "- Flash the audio board once over its own USB port (firmware/audio-board), then it runs on its own.",
      "- Phone pairing name: \"HackClock\". The clock board shows track title/artist on its \"Now playing\" page.",
      "- WiFi details are sent to the audio board by the clock over I2C - nothing to configure."]
for i, t in enumerate(an): ax.text(22, 88 - i * 7, t, fontsize=7)

# ---- power + chargers
ax.text(212, 96, "Power + charging", fontsize=8.5, fontweight="bold")
def blk(x, y, w, h, title, sub=""):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.5", fc=BOX, ec=INK, lw=1.4))
    ax.text(x + w / 2, y + h / 2 + (2.5 if sub else 0), title, ha="center", va="center", fontsize=7, fontweight="bold")
    if sub: ax.text(x + w / 2, y + h / 2 - 3.5, sub, ha="center", va="center", fontsize=5.8, color="#555")
blk(212, 70, 46, 16, "USB-C 5 V charger", "your own, 2-3 A")
ax.annotate("", (276, 78), (258, 78), arrowprops=dict(arrowstyle="->", color="#555", lw=1))
blk(276, 70, 44, 16, "J8 USB-C breakout", "in the tail")
line([(320, 78), (334, 78)]); label(334, 78, "+5V_IN (J8)", "right", PWR)
blk(212, 44, 60, 16, "Samsung watch puck", "middle of the roof, own adapter")
ax.text(212, 36, "The watch puck is NOT wired to the PCB: its cable runs inside the body and out", fontsize=6.2, color="#555")
ax.text(212, 31, "through the USB-A slot in the tail to its own adapter (or a multi-port charger).", fontsize=6.2, color="#555")

with PdfPages("schematic.pdf") as pdf:
    pdf.savefig(fig1, bbox_inches="tight"); pdf.savefig(fig2, bbox_inches="tight")
fig1.savefig("schematic.png", dpi=160, bbox_inches="tight")
fig1.savefig("../../docs/images/schematic.png", dpi=160, bbox_inches="tight")
fig2.savefig("schematic_audio.png", dpi=160, bbox_inches="tight")
fig2.savefig("../../docs/images/schematic_audio.png", dpi=160, bbox_inches="tight")
print("ok")
