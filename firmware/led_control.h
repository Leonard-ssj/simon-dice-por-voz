#pragma once

#include "vocabulario.h"

// ============================================================
// led_control.h — LEDs virtuales del juego
//
// No hay LEDs físicos en el kit MRD085A.
// Los LEDs se visualizan únicamente en el Web Panel (LEDPanel).
// Estas funciones envían mensajes Serial (LED:ROJO, LED:OFF)
// para que el browser actualice el panel visual.
// ============================================================

// Inicializa los LEDs (sin GPIO — solo inicialización lógica)
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
