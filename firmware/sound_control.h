#pragma once

#include "vocabulario.h"

// ============================================================
// sound_control.h — Tonos y feedback por speaker MAX98357A
//
// El amplificador MAX98357A recibe audio I2S del ESP32-S3.
// Usamos I2S_NUM_1 (el micrófono INMP441 usa I2S_NUM_0).
//
// ⚠️ Pines MAX98357A — verificar con el esquemático MRD085A
//    Los pines mostrados son la asignación típica para este tipo
//    de placa; ajustar si el kit tiene otra distribución.
// ============================================================

// Periférico I2S para el speaker (el mic usa I2S_NUM_0)
#define I2S_NUM_SPK       I2S_NUM_1

// Pines I2S del MAX98357A ⚠️ VERIFICAR con el kit físico
#define I2S_SPK_BCLK_PIN   5   // BCLK (bit clock)    ⚠️ VERIFICAR
#define I2S_SPK_WS_PIN     4   // LRC  (word select)  ⚠️ VERIFICAR
#define I2S_SPK_DOUT_PIN   6   // DIN  (data input)   ⚠️ VERIFICAR
#define I2S_SPK_SD_PIN     7   // SD   (shutdown/on)  ⚠️ VERIFICAR

// Parámetros de audio del speaker
#define SPK_SAMPLE_RATE    16000   // Hz
#define SPK_AMPLITUD       6000    // 0–32767 (volumen de los tonos)
#define SPK_CHUNK_SIZE     256     // muestras por escritura I2S

// Inicializa el speaker I2S
void sonidoInicializar();

// Reproduce un tono simple (onda cuadrada) a la frecuencia y duración indicadas
void sonidoBeep(int frecuenciaHz, int duracionMs);

// Tono asociado a cada color de la secuencia
void sonidoColor(Comando color);

// Feedback de respuesta correcta
void sonidoCorrecto();

// Feedback de error / respuesta incorrecta
void sonidoError();

// Melodía de inicio de juego
void sonidoInicio();

// Melodía de game over
void sonidoGameOver();

// Tono ascendente al subir de nivel
void sonidoNuevoNivel(int nivel);
