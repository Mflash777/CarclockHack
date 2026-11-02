#pragma once
// ---------------- HackClock v2 pin map (Seeed XIAO ESP32-S3) ----------------
//  XIAO | GPIO | Used for
//  D0   |  1   | Button resistor ladder (ADC): SNOOZE / MODE / UP / DOWN / TALK
//  D1   |  2   | TFT DC
//  D2   |  3   | TFT CS
//  D3   |  4   | Buzzers (2N3904 driver) - backup alarm sound
//  D4   |  5   | I2C SDA  -> DS3231 RTC, HT16K33 7-segment, audio board (0x42)
//  D5   |  6   | I2C SCL
//  D6   |  43  | Mic SCK  (INMP441)
//  D7   |  44  | Mic WS   (INMP441)
//  D8   |  7   | TFT SCK
//  D9   |  8   | Mic SD   (INMP441 data)
//  D10  |  9   | TFT MOSI
// TFT backlight (BLK) is dimmed by the audio board (GPIO4) on command over I2C.

#define PIN_BUTTONS   1
#define PIN_BUZZER    4
#define PIN_SDA       5
#define PIN_SCL       6
#define PIN_MIC_SCK   43
#define PIN_MIC_WS    44
#define PIN_MIC_SD    8

#define I2C_ADDR_SEG    0x70   // HT16K33 7-segment backpack
#define I2C_ADDR_AUDIO  0x42   // audio board (ESP32 WROVER, I2C slave)

// Resistor ladder: 10k pull-up to 3V3; each button pulls the node to GND through:
//   SNOOZE 0R ~0 mV | MODE 2k2 ~595 mV | UP 4k7 ~1055 mV | DOWN 10k ~1650 mV | TALK 15k ~1980 mV | none 3300 mV
#define LADDER_SNOOZE_MAX  300
#define LADDER_MODE_MAX    830
#define LADDER_UP_MAX      1350
#define LADDER_DOWN_MAX    1810
#define LADDER_TALK_MAX    2600

// If the mic records silence, flip this (some ESP32 I2S drivers swap L/R)
#define MIC_CHANNEL_FMT   I2S_CHANNEL_FMT_ONLY_LEFT
#define MIC_SHIFT         14     // 32-bit sample >> 14 -> 16-bit with ~+6 dB gain
