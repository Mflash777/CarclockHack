# HackClock GT - where to buy

Full table with links: [`BOM.csv`](../BOM.csv). Prices are US dollars and **exclude shipping and tax**.

**Two price tiers.** The CSV total (~$167) uses US retailers that ship quickly (Adafruit, SparkFun, Seeed, Amazon).
Buying the same parts from AliExpress/LCSC brings it to roughly $70-80, but takes 2-4 weeks. Search terms for that route:
`XIAO ESP32S3`, `ESP32-DevKitC-VE WROVER-E`, `2.0 inch IPS ST7789 240x320`, `HT16K33 7 segment 4 digit`, `DS3231 module`, `INMP441`, `MAX98357A`.

**Link status.** "verified" = I opened the product page and confirmed name/price/stock. "link found by search" = real listing, but price/stock not confirmed - check before ordering. "search link" = an Amazon search; any equivalent part works.

| Part | Link | Price | Status |
|---|---|---|---|
| Seeed XIAO ESP32-S3 | https://www.seeedstudio.com/XIAO-ESP32S3-p-5627.html | $7.49 | verified |
| ESP32-DevKitC-VE (WROVER-E) | https://shillehtek.com/products/esp32-devkitc-ve-8mb-flash-8mb-psram-presoldered | $24.99 | verified |
| same, Digikey | https://www.digikey.com/en/products/detail/espressif-systems/ESP32-DEVKITC-VE/12091812 | see site | WROVER-E, 8MB/8MB confirmed |
| 2.0" ST7789 TFT | https://www.sparkfun.com/tft-lcd-display-module-screen-2-0in-240x320-spi-interface.html | $18.95 | verified |
| 7-segment I2C (HT16K33) | https://www.adafruit.com/product/878 | $9.95 | verified |
| DS3231 RTC | https://www.adafruit.com/product/5188 | $13.95 | verified |
| INMP441 mic | https://shillehtek.com/products/inmp441-i2s-omnidirectional-microphone-module-with-soldering | $9.99 | verified |
| MAX98357A amp | https://www.adafruit.com/product/3006 | $5.95 | verified |
| 2" 4 ohm speaker | https://www.amazon.com/Gikfun-Speaker-Loudspeaker-Arduino-Replacement/dp/B081169PC5 | ~$8 | search |
| Passive buzzer WT-1205 | https://www.digikey.com/en/products/detail/soberton-inc/WT-1205/479674 | ~$1 each | externally driven, 5 V confirmed |
| 6x6x5 tactile switches | https://www.adafruit.com/product/367 | $2.50 | verified |
| 12 mm panel buttons | https://www.amazon.com/Clyxgs-Momentary-Thread-Button-Switch/dp/B07L1PYC2V | ~$8 | search |
| USB-C breakout | https://www.adafruit.com/product/4090 | $2.95 | verified |
| Dupont wires | https://www.amazon.com/ELEGOO-Dedicated-Multicolored-Male-Header-Connections/dp/B0H6F428L1 | ~$6 | search |
| PCB | https://jlcpcb.com (upload Gerbers) | ~$2 + ship | - |

Notes
- The Adafruit DS3231 (#3013) is out of stock; #5188 is the in-stock STEMMA QT version and works the same on I2C.
- Measure before printing: watch-puck diameter (pocket is 38.6 mm), TFT module outline, and the 12 mm buttons' hole size. The 6x6 switch may need a thin shim under the wing.
- Export Gerbers from `hardware/pcb/hackclock.kicad_pcb` in KiCad 8 (File > Fabrication Outputs) before ordering.
- Already owned: Samsung watch puck + adapter, 5 V USB-C charger. Not included: Home Assistant server.
