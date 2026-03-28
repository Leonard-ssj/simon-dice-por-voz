#pragma once

#include "vocabulario.h"

// ============================================================
// sound_control.h — Tonos y feedback por speaker MAX98357A
//
// El amplificador MAX98357A recibe audio I2S del ESP32-S3.
// Usamos I2S_NUM_1 (el micrófono INMP441 usa I2S_NUM_0).
//
// Pines → ver pines.h (fuente única de configuración GPIO)
// ============================================================

#include "pines.h"

// Periférico I2S para el speaker (el mic usa I2S_NUM_0)
#define I2S_NUM_SPK       I2S_NUM_1

// Aliases locales que apuntan a pines.h
#define I2S_SPK_BCLK_PIN   PIN_SPK_BCLK
#define I2S_SPK_WS_PIN     PIN_SPK_WS
#define I2S_SPK_DOUT_PIN   PIN_SPK_DIN
#define I2S_SPK_SD_PIN     PIN_SPK_SD

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
