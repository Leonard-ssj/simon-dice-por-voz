#pragma once

// ============================================================
// pines.h — Configuración central de pines GPIO — OKYN-G5806
//
// FUENTE ÚNICA de verdad para todos los pines del kit.
// Si un pin está mal, solo se cambia aquí.
//
// Kit: OKYSTAR OKYN-G5806
// Chip: ESP32-S3 N8R2 (8MB Flash, 2MB PSRAM Quad-SPI)
//
// ⚠️ ESTAS ASIGNACIONES SON ESTIMADAS.
//    Antes de quemar el firmware por primera vez, ejecutar
//    el sketch de diagnóstico (ver docs/hardware.md) para
//    confirmar cuáles son los pines reales del PCB.
//
// Pines internos NO disponibles en este chip:
//   GPIO 26-32  → SPI Flash / PSRAM (uso interno del chip)
//   GPIO 45, 46 → Strapping pins (boot), no usar como salida
//   GPIO 3      → Strapping pin (no usar)
// ============================================================


// ─────────────────────────────────────────────────────────────
//  MICRÓFONO — INMP441 (I2S digital, I2S_NUM_0)
//  Señales: BCLK = clock de bits, WS = canal L/R, SD = datos
// ─────────────────────────────────────────────────────────────
#define PIN_MIC_BCLK    12   // INMP441 SCK  (bit clock)    ⚠️ VERIFICAR
#define PIN_MIC_WS      13   // INMP441 WS   (word select)  ⚠️ VERIFICAR
#define PIN_MIC_DATA    11   // INMP441 SD   (data out)     ⚠️ VERIFICAR


// ─────────────────────────────────────────────────────────────
//  SPEAKER — Amplificador MAX98357A (I2S digital, I2S_NUM_1)
//  Señales: BCLK = clock, WS = canal, DIN = datos, SD = enable
// ─────────────────────────────────────────────────────────────
#define PIN_SPK_BCLK     5   // MAX98357A BCLK               ⚠️ VERIFICAR
#define PIN_SPK_WS       4   // MAX98357A LRC (word select)   ⚠️ VERIFICAR
#define PIN_SPK_DIN      6   // MAX98357A DIN (data in)       ⚠️ VERIFICAR
#define PIN_SPK_SD       7   // MAX98357A SD  (shutdown/on)   ⚠️ VERIFICAR
//   SD = HIGH → amplificador ON (conectar a este pin o a 3.3V fijo)


// ─────────────────────────────────────────────────────────────
//  PANTALLA — OLED SSD1306 0.91" (I2C)
//  Dirección I2C estándar: 0x3C (algunos módulos usan 0x3D)
// ─────────────────────────────────────────────────────────────
#define PIN_OLED_SDA    21   // I2C SDA  ⚠️ VERIFICAR
#define PIN_OLED_SCL    22   // I2C SCL  ⚠️ VERIFICAR


// ─────────────────────────────────────────────────────────────
//  BOTONES — SW1 y SW2 del kit (PTT para captura de voz)
//
//  GPIO 0 = botón BOOT del ESP32.
//    → Durante encendido entra al bootloader si está presionado.
//    → Después del boot funciona normal como input con pull-up.
//    → Usar con INPUT_PULLUP (LOW cuando se presiona).
//
//  GPIO 47 = pin de usuario, seguro en N8R2.
// ─────────────────────────────────────────────────────────────
#define PIN_BTN_SW1      0   // SW1 Volumen+ → PTT principal   ⚠️ VERIFICAR
#define PIN_BTN_SW2     47   // SW2 Volumen- → PTT alternativo ⚠️ VERIFICAR
//   Ambos configurados como INPUT_PULLUP: LOW = presionado

