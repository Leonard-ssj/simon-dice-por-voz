#include "led_control.h"
#include "serial_comm.h"
#include <Arduino.h>

// ============================================================
// led_control.cpp — LEDs virtuales via Serial
//
// No hay LEDs físicos. Cada llamada envía un mensaje Serial
// para que el Web Panel (LEDPanel) actualice el color visual.
//   ledEncender(CMD_ROJO)  → Serial: "LED:ROJO\n"
//   ledsApagar()           → Serial: "LED:OFF\n"
// ============================================================

static const char* _colorNombre(Comando color) {
    switch (color) {
        case CMD_ROJO:     return "ROJO";
        case CMD_VERDE:    return "VERDE";
        case CMD_AZUL:     return "AZUL";
        case CMD_AMARILLO: return "AMARILLO";
        default:           return "OFF";
    }
}

void ledInicializar() {
    // Sin GPIO — los LEDs son virtuales en el Web Panel
    ledsApagar();
}

void ledEncender(Comando color) {
    char buf[16];
    snprintf(buf, sizeof(buf), "LED:%s", _colorNombre(color));
    serialEnviar(buf);
}

void ledApagar(Comando color) {
    (void)color;
    serialEnviar("LED:OFF");
}

void ledsApagar() {
    serialEnviar("LED:OFF");
}

void ledParpadear(Comando color, int veces, int duracionMs) {
    for (int i = 0; i < veces; i++) {
        ledEncender(color);
        delay(duracionMs);
        ledsApagar();
        delay(duracionMs);
    }
}

void ledEfectoInicio() {
    Comando orden[] = {CMD_ROJO, CMD_VERDE, CMD_AZUL, CMD_AMARILLO};
    for (int i = 0; i < 4; i++) {
        ledEncender(orden[i]);
        delay(150);
        ledsApagar();
        delay(50);
    }
    // Todos juntos en secuencia rápida
    for (int i = 0; i < 4; i++) {
        ledEncender(orden[i]);
        delay(100);
    }
    delay(300);
    ledsApagar();
}

void ledEfectoGameOver() {
    for (int r = 0; r < 3; r++) {
        for (int i = 0; i < 4; i++) {
            ledEncender(COLORES_VALIDOS[i]);
            delay(60);
        }
        ledsApagar();
        delay(150);
    }
}
