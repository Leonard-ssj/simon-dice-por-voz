// ============================================================
// simon_dice.ino — Entry point del juego Simon Dice por Voz
// Hardware: Kit OKYN-G5806 (ESP32-S3 + INMP441 + MAX98357A)
// Fase 1: audio → USB Serial → Python/Whisper → comando → ESP32
// ============================================================

#include "vocabulario.h"
#include "game_engine.h"
#include "led_control.h"
#include "sound_control.h"
#include "audio_capture.h"
#include "serial_comm.h"

// Instancia global del motor del juego
GameEngine juego;

// ---- setup ----
void setup() {
    serialInicializar();
    ledInicializar();
    sonidoInicializar();
    audioInicializar();

    // Efecto de inicio para confirmar que el hardware funciona
    ledEfectoInicio();
    sonidoInicio();

    juego.iniciar();
    serialEnviarReady();

    Serial.println("// Simon Dice por Voz — Fase 1");
    Serial.println("// Di START para comenzar");
}

// ---- loop ----
void loop() {
    static char lineaBuf[64];

    // Leer línea cruda del Serial
    if (serialLeer(lineaBuf, sizeof(lineaBuf))) {
        // PTT_INICIO / PTT_FIN: pausan el timeout mientras el browser transcribe
        if (strcmp(lineaBuf, "PTT_INICIO") == 0) {
            juego.pausarTimeout();
        } else if (strcmp(lineaBuf, "PTT_FIN") == 0) {
            juego.reanudarTimeout();
        } else {
            // Comando de voz: pasar al motor del juego
            Comando cmd = stringAComando(lineaBuf);
            if (cmd != CMD_DESCONOCIDO) {
                serialEnviarDetectado(cmd);
                juego.procesarComando(cmd);
            }
        }
    }

    // Actualizar la máquina de estados (maneja timings internos)
    juego.update();

    // Pequeña pausa para no saturar el Serial
    delay(10);
}
