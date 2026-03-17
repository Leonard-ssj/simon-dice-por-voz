#include "sound_control.h"
#include <Arduino.h>

// ============================================================
// sound_control.cpp — Implementación de tonos por speaker
//
// El kit OKYN-G5806 usa amplificador MAX98357A conectado por I2S.
// Usamos la librería ESP32-audioI2S o driver ledc como fallback.
//
// NOTA: Si ESP32-audioI2S no está disponible, usar ledcWriteTone()
//       con un pin de salida PWM como alternativa temporal.
// ============================================================

// Frecuencias base para cada color (Do, Mi, Sol, Si)
#define FREQ_ROJO      262  // Do4
#define FREQ_VERDE     330  // Mi4
#define FREQ_AZUL      392  // Sol4
#define FREQ_AMARILLO  494  // Si4

// Frecuencias de feedback
#define FREQ_CORRECTO  1047  // Do6
#define FREQ_ERROR     196   // Sol3 bajo
#define FREQ_INICIO    880   // La5

// Canal LEDC para PWM (fallback si no hay I2S disponible)
#define LEDC_CANAL     0
#define LEDC_RESOLUCION 8
#define PIN_SPEAKER_PWM 8  // ⚠ Verificar con el kit físico

void sonidoInicializar() {
    // Configurar canal LEDC como fallback
    ledcSetup(LEDC_CANAL, 1000, LEDC_RESOLUCION);
    ledcAttachPin(PIN_SPEAKER_PWM, LEDC_CANAL);
}

void sonidoBeep(int frecuenciaHz, int duracionMs) {
    ledcWriteTone(LEDC_CANAL, frecuenciaHz);
    delay(duracionMs);
    ledcWriteTone(LEDC_CANAL, 0);
}

void sonidoColor(Comando color) {
    int freq = 0;
    switch (color) {
        case CMD_ROJO:     freq = FREQ_ROJO;     break;
        case CMD_VERDE:    freq = FREQ_VERDE;    break;
        case CMD_AZUL:     freq = FREQ_AZUL;     break;
        case CMD_AMARILLO: freq = FREQ_AMARILLO; break;
        default: return;
    }
    sonidoBeep(freq, 400);
}

void sonidoCorrecto() {
    sonidoBeep(FREQ_CORRECTO, 150);
    delay(50);
    sonidoBeep(FREQ_CORRECTO, 300);
}

void sonidoError() {
    sonidoBeep(FREQ_ERROR, 200);
    delay(100);
    sonidoBeep(FREQ_ERROR, 400);
}

void sonidoInicio() {
    // Escala ascendente corta
    int notas[] = {262, 330, 392, 523};
    for (int i = 0; i < 4; i++) {
        sonidoBeep(notas[i], 150);
        delay(30);
    }
}

void sonidoGameOver() {
    // Escala descendente lenta
    int notas[] = {523, 440, 349, 262};
    for (int i = 0; i < 4; i++) {
        sonidoBeep(notas[i], 250);
        delay(50);
    }
}

void sonidoNuevoNivel(int nivel) {
    // Más notas = nivel más alto
    int repeticiones = min(nivel, 4);
    for (int i = 0; i < repeticiones; i++) {
        sonidoBeep(FREQ_INICIO, 100);
        delay(80);
    }
}
