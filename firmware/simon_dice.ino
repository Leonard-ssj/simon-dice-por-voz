// ============================================================
// simon_dice.ino — Entry point del juego Simon Dice por Voz
// Hardware: Kit MRD085A (ESP32-S3-N16R8 + INMP441 + MAX98357A
//           + OLED 0.91" + botones SW1/SW2)
//
// Flujo de voz (dos modos, se eligen automáticamente):
//   Modo A — Botón físico (SW1/SW2) + INMP441:
//     botón presionado → captura audio en PSRAM → envía base64
//     por Serial → browser → servidor_voz (Whisper Python)
//   Modo B — Teclado (barra espaciadora) + mic del browser:
//     WASM Whisper en browser o servidor_voz según disponibilidad
//     → "ROJO\n" por Serial → firmware
// ============================================================

#include "vocabulario.h"
#include "game_engine.h"
#include "led_control.h"
#include "sound_control.h"
#include "audio_capture.h"
#include "serial_comm.h"
#include "oled_display.h"
#include "botones.h"

// Instancia global del motor del juego
GameEngine juego;

// Estado del juego que se refleja en el OLED
static char  _estadoOled[16]    = "IDLE";
static int   _nivelOled         = 1;
static int   _puntuacionOled    = 0;
static char  _esperadoOled[16]  = "";

// Actualiza el OLED con el estado actual
static void _actualizarOled() {
    oledMostrarEstado(_estadoOled, _nivelOled, _puntuacionOled, _esperadoOled);
}

// ---- setup ----
void setup() {
    serialInicializar();

    // OLED — arrancar primero para mostrar progreso de inicio
    if (oledInicializar()) {
        oledMostrarBienvenida();
    }

    ledInicializar();
    sonidoInicializar();
    audioInicializar();       // inicia I2S mic + alloc PSRAM buffer

    botonesSetJuego(&juego);
    botonesInicializar();

    // Efecto de inicio para confirmar que el hardware funciona
    ledEfectoInicio();
    sonidoInicio();

    juego.iniciar();
    serialEnviarReady();

    Serial.println("// Simon Dice por Voz");
    Serial.println("// Botones SW1/SW2 = PTT fisico");
    Serial.println("// Di START o presiona boton para comenzar");
}

// ---- loop ----
void loop() {
    static char lineaBuf[64];

    // 1. Leer línea cruda del Serial (browser → ESP32)
    if (serialLeer(lineaBuf, sizeof(lineaBuf))) {

        if (strcmp(lineaBuf, "PTT_INICIO") == 0) {
            // Browser presionó barra espaciadora — pausar timeout
            juego.pausarTimeout();

        } else if (strcmp(lineaBuf, "PTT_FIN") == 0) {
            // Browser soltó la barra — reanudar timeout
            juego.reanudarTimeout();

        } else {
            // Comando de voz (texto plano: ROJO, START, etc.)
            Comando cmd = stringAComando(lineaBuf);
            if (cmd != CMD_DESCONOCIDO) {
                serialEnviarDetectado(cmd);
                juego.procesarComando(cmd);
            }
        }
    }

    // 2. PTT físico: leer botones SW1/SW2
    botonesUpdate();   // detecta press/release; captura audio internamente

    // 3. Acumular audio mientras el botón está presionado
    if (audioCapturaActiva()) {
        audioCapturaLoop();
    }

    // 4. Actualizar máquina de estados del juego
    EstadoJuego estadoAnterior = juego.getEstado();
    juego.update();
    EstadoJuego estadoActual   = juego.getEstado();

    // 5. Actualizar OLED si cambió el estado
    if (estadoActual != estadoAnterior) {
        const char* nombres[] = {
            "IDLE", "SHOWING", "LISTENING", "EVALUATING",
            "CORRECT", "LEVEL_UP", "WRONG", "GAMEOVER", "PAUSA"
        };
        if ((int)estadoActual < 9) {
            strncpy(_estadoOled, nombres[(int)estadoActual], sizeof(_estadoOled) - 1);
        }
        _nivelOled      = juego.getNivel();
        _puntuacionOled = juego.getPuntuacion();

        if (estadoActual == ESTADO_LISTENING) {
            Comando esp = juego.getColorEsperado();
            strncpy(_esperadoOled, comandoAString(esp), sizeof(_esperadoOled) - 1);
        } else if (estadoActual == ESTADO_GAME_OVER) {
            _esperadoOled[0] = '\0';
            oledMostrarGameOver(_puntuacionOled);
        } else if (estadoActual == ESTADO_SHOWING_SEQUENCE) {
            _esperadoOled[0] = '\0';
        }

        if (estadoActual != ESTADO_GAME_OVER) {
            _actualizarOled();
        }
    }

    delay(10);
}
