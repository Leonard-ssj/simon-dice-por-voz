#include "led_control.h"
#include <Arduino.h>

// ============================================================
// led_control.cpp — Implementación del control de LEDs
// ============================================================

// Mapeo de color a pin GPIO
static int _pinDeColor(Comando color) {
    switch (color) {
        case CMD_ROJO:     return PIN_LED_ROJO;
        case CMD_VERDE:    return PIN_LED_VERDE;
        case CMD_AZUL:     return PIN_LED_AZUL;
        case CMD_AMARILLO: return PIN_LED_AMARILLO;
        default:           return -1;
    }
}

void ledInicializar() {
    pinMode(PIN_LED_ROJO,      OUTPUT);
    pinMode(PIN_LED_VERDE,     OUTPUT);
    pinMode(PIN_LED_AZUL,      OUTPUT);
    pinMode(PIN_LED_AMARILLO,  OUTPUT);
    ledsApagar();
}

void ledEncender(Comando color) {
    int pin = _pinDeColor(color);
    if (pin >= 0) digitalWrite(pin, HIGH);
}

void ledApagar(Comando color) {
    int pin = _pinDeColor(color);
    if (pin >= 0) digitalWrite(pin, LOW);
}

void ledsApagar() {
    digitalWrite(PIN_LED_ROJO,     LOW);
    digitalWrite(PIN_LED_VERDE,    LOW);
    digitalWrite(PIN_LED_AZUL,     LOW);
    digitalWrite(PIN_LED_AMARILLO, LOW);
}

void ledParpadear(Comando color, int veces, int duracionMs) {
    for (int i = 0; i < veces; i++) {
        ledEncender(color);
        delay(duracionMs);
        ledApagar(color);
        delay(duracionMs);
    }
}

void ledEfectoInicio() {
    Comando orden[] = {CMD_ROJO, CMD_VERDE, CMD_AZUL, CMD_AMARILLO};
    for (int i = 0; i < 4; i++) {
        ledEncender(orden[i]);
        delay(150);
        ledApagar(orden[i]);
        delay(50);
    }
    // Todos juntos
    for (int i = 0; i < 4; i++) ledEncender(orden[i]);
    delay(400);
    ledsApagar();
}

void ledEfectoGameOver() {
    for (int r = 0; r < 3; r++) {
        for (int i = 0; i < 4; i++) ledEncender(COLORES_VALIDOS[i]);
        delay(150);
        ledsApagar();
        delay(150);
    }
}
