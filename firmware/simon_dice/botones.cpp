#include "botones.h"
#include "audio_capture.h"
#include "serial_comm.h"
#include "game_engine.h"
#include <Arduino.h>

// ============================================================
// botones.cpp — Implementación del PTT físico
// ============================================================

// Estado interno de los botones
static bool          _pttActivo    = false;
static unsigned long _ultimoFlanco = 0;

// Referencia al motor del juego para pausar/reanudar el timeout.
// Se asigna desde simon_dice.ino mediante botonesSetJuego().
static GameEngine* _juego = nullptr;

void botonesSetJuego(GameEngine* juego) {
    _juego = juego;
}

void botonesInicializar() {
    pinMode(PIN_BTN_SW1, INPUT_PULLUP);
    pinMode(PIN_BTN_SW2, INPUT_PULLUP);
    _pttActivo    = false;
    _ultimoFlanco = 0;
}

bool botonPTTPresionado() {
    return _pttActivo;
}

bool botonesUpdate() {
    unsigned long ahora = millis();

    // Anti-rebote: ignorar flancos muy seguidos
    if (ahora - _ultimoFlanco < BTN_DEBOUNCE_MS) return false;

    // Algún botón presionado = LOW (PULLUP activo)
    bool presionado = (digitalRead(PIN_BTN_SW1) == LOW ||
                       digitalRead(PIN_BTN_SW2) == LOW);

    if (presionado && !_pttActivo) {
        // ── Flanco descendente: botón presionado ──
        _pttActivo    = true;
        _ultimoFlanco = ahora;

        // 1. Pausar el timeout del juego mientras el jugador habla
        if (_juego) _juego->pausarTimeout();

        // 2. Empezar a capturar audio del INMP441 en PSRAM
        audioCapturaIniciar();

        // 3. Notificar al browser: mostrará indicador de grabación
        serialEnviar("BTN_INICIO");
        return true;
    }

    if (!presionado && _pttActivo) {
        // ── Flanco ascendente: botón suelto ──
        _pttActivo    = false;
        _ultimoFlanco = ahora;

        // 4. Detener captura y enviar audio en base64 por Serial
        //    El browser lo procesa con servidor_voz (Whisper) o WASM
        audioCapturaPararYEnviar();

        // Nota: juego.reanudarTimeout() se llamará cuando el browser
        // devuelva el comando ("PTT_FIN\n") o un color ("ROJO\n").
        return true;
    }

    return false;
}
