#pragma once

#include "vocabulario.h"

// ============================================================
// sound_control.h — Tonos y feedback por speaker MAX98357A
// El speaker usa I2S integrado en el kit OKYN-G5806
// ============================================================

// Inicializa el speaker I2S
void sonidoInicializar();

// Reproduce un tono corto asociado a cada color
void sonidoColor(Comando color);

// Tono de respuesta correcta
void sonidoCorrecto();

// Tono de error / respuesta incorrecta
void sonidoError();

// Tono de inicio de juego
void sonidoInicio();

// Tono de game over
void sonidoGameOver();

// Tono de nivel superado
void sonidoNuevoNivel(int nivel);

// Beep simple (frecuencia en Hz, duración en ms)
void sonidoBeep(int frecuenciaHz, int duracionMs);
