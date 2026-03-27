#pragma once

#include "game_engine.h"

// ============================================================
// botones.h — PTT físico con los botones del kit MRD085A
//
// SW1 (音量+ / volumen+): botón principal PTT
// SW2 (音量- / volumen-): botón alternativo PTT
//
// Al presionar → ESP32 pausa el timeout y empieza a capturar
//                audio del INMP441 hacia el buffer en PSRAM.
// Al soltar     → ESP32 detiene la captura, envía el audio
//                por Serial (base64) para que el browser
//                lo procese con Whisper.
//
// El PTT por teclado (barra espaciadora en el panel web) sigue
// funcionando en paralelo — no se excluyen mutuamente.
//
// ⚠️ Pines GPIO — verificar con el esquemático del kit MRD085A
// ============================================================

// Pines GPIO de los botones ⚠️ VERIFICAR con el kit físico
#define PIN_BTN_SW1     0    // 音量+ → PTT principal  ⚠️ VERIFICAR
#define PIN_BTN_SW2     35   // 音量- → PTT alternativo ⚠️ VERIFICAR

// Debounce — tiempo mínimo entre detección de flancos (ms)
#define BTN_DEBOUNCE_MS  50

// ---- API pública ----

// Asigna la referencia al motor del juego (llamar antes de botonesInicializar)
void botonesSetJuego(GameEngine* juego);

// Inicializa los pines como INPUT_PULLUP
void botonesInicializar();

// Llamar en cada loop() antes de juego.update().
// Detecta cambios de estado y dispara captura de audio.
// Retorna true si hubo un evento de PTT (presión o liberación).
bool botonesUpdate();

// Retorna true si algún botón PTT está presionado en este momento
bool botonPTTPresionado();
