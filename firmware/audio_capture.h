#pragma once

#include <stdint.h>
#include <stddef.h>

// ============================================================
// audio_capture.h — Captura de audio por I2S (micrófono INMP441)
// El micrófono está integrado en el kit OKYN-G5806
// ============================================================

// Configuración I2S del micrófono (integrado en el kit)
// ⚠ Verificar pines exactos con documentación del OKYN-G5806
#define I2S_NUM_MIC      I2S_NUM_0
#define I2S_SCK_PIN      12    // BCLK — verificar con kit
#define I2S_WS_PIN       13    // LRCLK — verificar con kit
#define I2S_SD_PIN       11    // DOUT del micrófono — verificar con kit

// Parámetros de captura
#define SAMPLE_RATE      16000   // Hz — requerido por Whisper
#define BITS_PER_SAMPLE  16      // bits por muestra
#define BUFFER_SIZE      1024    // muestras por buffer
#define CHUNK_DURACION   2000    // ms de audio por chunk enviado (Fase 1)

// Umbral VAD (Voice Activity Detection) — ajustar según ruido del entorno
#define VAD_UMBRAL       500     // amplitud mínima para considerar voz

// Inicializa el periférico I2S para el micrófono
void audioInicializar();

// Retorna true si hay voz activa en este momento (VAD simple)
bool audioHayVoz();

// Captura un chunk de audio y lo envía por Serial (Fase 1)
// Retorna true si se capturó y envió correctamente
bool audioCapturarYEnviar();

// Espera a que empiece la voz y captura hasta el silencio
// duracionMaxMs: tiempo máximo de espera antes de rendirse
// Retorna true si se detectó y capturó voz
bool audioEsperarVoz(int duracionMaxMs);

// Lee muestras crudas en el buffer
// Retorna cantidad de muestras leídas
size_t audioLeerMuestras(int16_t* buffer, size_t cantMuestras);
