#pragma once

#include <stdint.h>
#include <stddef.h>

// ============================================================
// audio_capture.h — Captura de audio I2S (micrófono INMP441)
//
// Dos modos de operación:
//
//   PTT físico (nuevo): el jugador presiona un botón → captura
//     audio en buffer PSRAM → al soltar envía base64 por Serial
//     → browser recibe y usa Whisper para transcribir.
//
//   Stream continuo (Fase 2): captura + envía VAD + chunks
//     (flujo original, no usado en Fase 1 con Serial).
//
// Pines → ver pines.h (fuente única de configuración GPIO)
// ============================================================

#include "pines.h"

// Periférico I2S del micrófono
#define I2S_NUM_MIC      I2S_NUM_0

// Aliases locales que apuntan a pines.h
#define I2S_SCK_PIN      PIN_MIC_BCLK
#define I2S_WS_PIN       PIN_MIC_WS
#define I2S_SD_PIN       PIN_MIC_DATA

// Parámetros de captura
#define SAMPLE_RATE      16000   // Hz — requerido por Whisper
#define BITS_PER_SAMPLE  16      // bits por muestra
#define BUFFER_SIZE      512     // muestras por lectura DMA

// Buffer PTT en PSRAM — máximo 5 segundos de audio
// El N8R2 tiene 2MB PSRAM. 5s = 160 000 bytes (156 KB), cabe con margen.
#define AUDIO_PTT_MAX_MUESTRAS   (SAMPLE_RATE * 5)             // 80 000 muestras
#define AUDIO_PTT_MAX_BYTES      (AUDIO_PTT_MAX_MUESTRAS * 2)  // 160 000 bytes

// Umbral VAD básico (amplitud mínima para detectar voz en modo stream)
#define VAD_UMBRAL       500

// ---- Inicialización ----

// Inicializa el periférico I2S y asigna buffer PSRAM
void audioInicializar();

// ---- Modo PTT físico (botón) ----

// Inicia la captura PTT: empieza a acumular audio en el buffer PSRAM
void audioCapturaIniciar();

// Detiene la captura y envía el audio por Serial en formato base64.
// Protocolo:
//   "AUDIO:START:<n_bytes>\n"   — n_bytes = muestras × 2
//   "<línea base64 de 60 chars>\n"  × muchas líneas
//   "AUDIO:END\n"
// El browser recibe y reenvía a servidor_voz para Whisper.
void audioCapturaPararYEnviar();

// Retorna true si la captura PTT está activa
bool audioCapturaActiva();

// Llamar desde loop() mientras audioCapturaActiva() sea true.
// Lee el DMA en modo no bloqueante y acumula en el buffer PSRAM.
void audioCapturaLoop();

// ---- Modo stream (Fase 2 / referencia) ----

// Retorna true si hay voz activa (VAD simple)
bool audioHayVoz();

// Lee muestras crudas en el buffer externo
size_t audioLeerMuestras(int16_t* buffer, size_t cantMuestras);
