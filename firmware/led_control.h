#pragma once

#include "vocabulario.h"

// ============================================================
// led_control.h — Control de los 4 LEDs del juego
// IMPORTANTE: Verificar pines con el kit físico OKYN-G5806
// ============================================================

// Pines GPIO — ajustar según el kit físico
#define PIN_LED_ROJO      15
#define PIN_LED_VERDE     16
#define PIN_LED_AZUL      17
#define PIN_LED_AMARILLO  18

// Inicializa los pines de los LEDs
void ledInicializar();

// Enciende el LED correspondiente al color
void ledEncender(Comando color);

// Apaga el LED correspondiente al color
void ledApagar(Comando color);

// Apaga todos los LEDs
void ledsApagar();

// Parpadea un LED N veces (para feedback de error, inicio, etc.)
void ledParpadear(Comando color, int veces, int duracionMs);

// Efecto de inicio: todos los LEDs encienden en secuencia
void ledEfectoInicio();

// Efecto de game over: todos parpadean rápido
void ledEfectoGameOver();
